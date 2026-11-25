import base64
import logging
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from PIL import Image
from playwright.sync_api import BrowserContext, Page, sync_playwright

from ..config import PROJECTS_DIR
from .gemini_service import build_full_image_prompt

logger = logging.getLogger(__name__)

BROWSER_PROFILE_DIR = PROJECTS_DIR / "_browser_profile"
GEMINI_WEB_URL = "https://gemini.google.com/app"
_BROWSER_LOCK = threading.Lock()

PROMPT_SELECTORS = [
    "div.ql-editor[contenteditable='true']",
    "rich-textarea div[contenteditable='true']",
    "div[contenteditable='true'][role='textbox']",
    "textarea[aria-label*='prompt' i]",
    "[aria-label*='Enter a prompt' i]",
]


class BrowserImageError(Exception):
    """User-friendly error raised during Playwright Gemini Web image generation."""


def _launch_context(pw) -> BrowserContext:
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    common_kwargs: Dict[str, Any] = {
        "user_data_dir": str(BROWSER_PROFILE_DIR),
        "headless": False,
        "viewport": {"width": 1280, "height": 860},
        "accept_downloads": True,
    }
    for channel in ("chrome", "msedge", None):
        try:
            kwargs = dict(common_kwargs)
            if channel:
                kwargs["channel"] = channel
            ctx = pw.chromium.launch_persistent_context(**kwargs)
            logger.info("Launched persistent Playwright browser (channel=%s)", channel or "chromium")
            return ctx
        except Exception as exc:
            logger.warning("Could not launch browser channel=%s: %s", channel, exc)
    raise BrowserImageError(
        "Could not launch Chrome, Edge, or Chromium. Run 'playwright install chromium' in backend/.venv."
    )


def _find_prompt_box(page: Page):
    for sel in PROMPT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=400):
                return loc
        except Exception:
            continue
    return None


def _is_signed_in(page: Page) -> bool:
    try:
        cur_url = page.url.lower()
        if "accounts.google.com" in cur_url:
            return False
        state = page.evaluate(
            """() => {
                const isVis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
                };
                const hasAccount = Array.from(document.querySelectorAll('a, button')).some(
                    el => /google account/i.test(el.getAttribute('aria-label') || '') && isVis(el)
                );
                const hasSignIn = Array.from(document.querySelectorAll('a, button')).some(el => {
                    const txt = (el.innerText || '').trim().toLowerCase();
                    const href = (el.getAttribute('href') || '').toLowerCase();
                    return isVis(el) && (txt === 'sign in' || href.includes('servicelogin'));
                });
                return { hasAccount, hasSignIn };
            }"""
        )
        if state.get("hasAccount"):
            return True
        if state.get("hasSignIn"):
            return False
        return _find_prompt_box(page) is not None
    except Exception:
        return False


def _wait_for_login(
    page: Page,
    status_cb: Optional[Callable[[str], None]] = None,
    timeout_sec: int = 300,
) -> None:
    deadline = time.time() + timeout_sec
    notified = False
    while time.time() < deadline:
        if _is_signed_in(page) and _find_prompt_box(page) is not None:
            return
        if not notified and status_cb:
            status_cb(
                "Please sign in to your Google account in the opened Chrome window to enable Gemini image creation..."
            )
            notified = True
        time.sleep(2.0)
    raise BrowserImageError(
        "Timed out waiting for Google sign-in on gemini.google.com. Click '1. Open Gemini & Sign In' and sign in first."
    )


def _collect_large_images(page: Page) -> List[Dict[str, Any]]:
    try:
        return page.evaluate(
            """() => {
                const imgs = Array.from(document.querySelectorAll('img'));
                return imgs
                    .filter(img => {
                        const w = img.naturalWidth || 0;
                        const h = img.naturalHeight || 0;
                        const src = img.currentSrc || img.src || '';
                        if (!src || w < 360 || h < 240) return false;
                        if (src.includes('googleusercontent.com/a/') || src.includes('gstatic.com/images/branding')) return false;
                        return true;
                    })
                    .map(img => ({
                        src: img.currentSrc || img.src || '',
                        width: img.naturalWidth,
                        height: img.naturalHeight,
                    }));
            }"""
        )
    except Exception:
        return []


def _save_as_16_9_png(raw_bytes: bytes, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(raw_bytes)) as img:
        rgb = img.convert("RGB")
        w, h = rgb.size
        target_ratio = 16.0 / 9.0
        cur_ratio = w / max(1, h)

        if cur_ratio > target_ratio + 0.02:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            rgb = rgb.crop((left, 0, left + new_w, h))
        elif cur_ratio < target_ratio - 0.02:
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            rgb = rgb.crop((0, top, w, top + new_h))

        out_w = 1920 if rgb.width >= 1600 else 1280
        out_h = 1080 if out_w == 1920 else 720
        rgb = rgb.resize((out_w, out_h), Image.Resampling.LANCZOS)
        rgb.save(output_path, format="PNG")
    return output_path


def _extract_new_image_bytes(
    page: Page,
    context: BrowserContext,
    new_src: str,
) -> bytes:
    # 1. Try Gemini's full-size download button near the latest image
    try:
        dl_btns = page.locator("button[aria-label*='Download' i], button[mattooltip*='Download' i]")
        count = dl_btns.count()
        if count > 0:
            last_btn = dl_btns.nth(count - 1)
            if last_btn.is_visible(timeout=1000):
                with page.expect_download(timeout=12000) as dl_info:
                    last_btn.click()
                download = dl_info.value
                tmp_path = download.path()
                if tmp_path and Path(tmp_path).exists():
                    return Path(tmp_path).read_bytes()
    except Exception as exc:
        logger.debug("Download button fallback triggered: %s", exc)

    # 2. Data URI
    if new_src.startswith("data:image/"):
        _, b64_part = new_src.split(",", 1)
        return base64.b64decode(b64_part)

    # 3. Direct authenticated HTTP fetch via browser context
    if new_src.startswith("http"):
        resp = context.request.get(new_src, timeout=30000)
        if resp.ok:
            return resp.body()

    # 4. Blob URL or fallback: element screenshot of the matching <img>
    img_loc = page.locator(f"img[src='{new_src}']").last
    if img_loc.count() > 0:
        return img_loc.screenshot(type="png")

    raise BrowserImageError("Could not extract image bytes from Gemini Web response.")


def _submit_prompt_and_save(
    page: Page,
    context: BrowserContext,
    prompt_text: str,
    output_path: Path,
    status_cb: Optional[Callable[[str], None]] = None,
) -> Path:
    if not _is_signed_in(page):
        _wait_for_login(page, status_cb=status_cb)

    prompt_box = _find_prompt_box(page)
    if prompt_box is None:
        _wait_for_login(page, status_cb=status_cb)
        prompt_box = _find_prompt_box(page)
        if prompt_box is None:
            raise BrowserImageError("Could not find the Gemini Web prompt box.")

    before_srcs: Set[str] = {item["src"] for item in _collect_large_images(page)}
    before_resp_count = page.locator("model-response").count()

    prompt_box.click()
    time.sleep(0.3)
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.insert_text(prompt_text)
    time.sleep(0.6)

    sent = False
    for send_sel in (
        "button[aria-label*='Send' i]",
        "button.send-button",
        "button[mattooltip*='Send' i]",
    ):
        try:
            btn = page.locator(send_sel).last
            if btn.is_visible(timeout=500) and btn.is_enabled():
                btn.click()
                sent = True
                break
        except Exception:
            continue
    if not sent:
        page.keyboard.press("Enter")

    deadline = time.time() + 95
    found_src: Optional[str] = None
    while time.time() < deadline:
        cur_url = page.url.lower()
        if "accounts.google.com" in cur_url or "sorry/index" in cur_url:
            if status_cb:
                status_cb(
                    "Google sign-in or verification appeared in the browser window. Please complete it there to continue..."
                )
            time.sleep(2.5)
            continue

        current_imgs = _collect_large_images(page)
        for item in reversed(current_imgs):
            if item["src"] not in before_srcs:
                found_src = item["src"]
                break
        if found_src:
            time.sleep(2.5)
            latest_imgs = _collect_large_images(page)
            for item in reversed(latest_imgs):
                if item["src"] not in before_srcs:
                    found_src = item["src"]
                    break
            break

        # Detect immediate refusal / signed-out text response
        try:
            if page.locator("model-response").count() > before_resp_count:
                latest_txt = page.locator("model-response").last.inner_text().strip()
                low = latest_txt.lower()
                if any(
                    marker in low
                    for marker in (
                        "might be signed out",
                        "can't create any",
                        "cannot create images",
                        "unable to generate",
                        "i can't generate images",
                    )
                ):
                    raise BrowserImageError(f"Gemini Web responded: {latest_txt[:220]}")
        except BrowserImageError:
            raise
        except Exception:
            pass

        time.sleep(1.5)

    if not found_src:
        raise BrowserImageError(
            "Timed out waiting for Gemini Web to render an image. "
            "Check the browser window for any error, refusal, or verification prompt."
        )

    raw_bytes = _extract_new_image_bytes(page, context, found_src)
    return _save_as_16_9_png(raw_bytes, output_path)


def open_login_browser(timeout_sec: int = 300) -> Dict[str, Any]:
    """
    Opens a visible browser window pointed at gemini.google.com/app so the user can
    log in once and persist their session cookies.
    """
    if not _BROWSER_LOCK.acquire(blocking=False):
        raise BrowserImageError("A Gemini browser session is already open.")
    try:
        with sync_playwright() as pw:
            context = _launch_context(pw)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(GEMINI_WEB_URL, wait_until="domcontentloaded", timeout=45000)
                time.sleep(2.0)

                # If currently signed out, click the Sign in link automatically to open Google login
                if not _is_signed_in(page):
                    try:
                        sign_in_btn = page.locator("a[href*='ServiceLogin'], button:has-text('Sign in'), a:has-text('Sign in')").first
                        if sign_in_btn.is_visible(timeout=2000):
                            sign_in_btn.click()
                    except Exception:
                        pass

                deadline = time.time() + timeout_sec
                logged_in = False
                while time.time() < deadline:
                    if context.pages == []:
                        break
                    if _is_signed_in(page) and _find_prompt_box(page) is not None:
                        logged_in = True
                        time.sleep(2.5)
                        break
                    time.sleep(1.5)

                return {
                    "logged_in": logged_in,
                    "message": (
                        "Gemini Web session is signed in and saved! Now click '2. Generate All via Browser'."
                        if logged_in
                        else "Browser closed before Google sign-in completed."
                    ),
                }
            finally:
                context.close()
    finally:
        _BROWSER_LOCK.release()


def generate_images_via_browser(
    scenes: List[Dict[str, Any]],
    character_bible: str,
    images_dir: Path,
    force_regenerate: bool,
    on_scene_done: Callable[[int, Path], None],
    status_cb: Callable[[int, int, str], None],
) -> None:
    """
    Generates missing (or all, if force_regenerate) scene images using the logged-in
    gemini.google.com web interface via a visible Playwright browser.
    """
    if not _BROWSER_LOCK.acquire(blocking=False):
        raise BrowserImageError(
            "Another Gemini browser session is already active. Please wait for it to finish."
        )

    try:
        to_process = [
            sc
            for sc in scenes
            if force_regenerate
            or not sc.get("image_path")
            or not Path(sc["image_path"]).exists()
        ]
        total = len(scenes)
        already_done = total - len(to_process)

        if not to_process:
            status_cb(total, total, "All scene images already exist!")
            return

        with sync_playwright() as pw:
            context = _launch_context(pw)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                status_cb(already_done, total, "Opening gemini.google.com in browser...")
                page.goto(GEMINI_WEB_URL, wait_until="domcontentloaded", timeout=45000)

                _wait_for_login(
                    page,
                    status_cb=lambda msg: status_cb(already_done, total, msg),
                )

                completed = already_done
                for idx_in_batch, sc in enumerate(to_process):
                    scene_num = sc["scene_index"]
                    out_png = images_dir / f"scene_{scene_num:03d}.png"

                    if idx_in_batch > 0 and idx_in_batch % 8 == 0:
                        page.goto(GEMINI_WEB_URL, wait_until="domcontentloaded", timeout=45000)
                        _wait_for_login(
                            page,
                            status_cb=lambda msg: status_cb(completed, total, msg),
                        )

                    status_cb(
                        completed,
                        total,
                        f"Generating Scene {scene_num} via Gemini Web Browser...",
                    )
                    full_prompt = build_full_image_prompt(sc["image_prompt"], character_bible)
                    web_prompt = (
                        f"Generate a 16:9 widescreen image (no text, no words, no watermarks): "
                        f"{full_prompt}"
                    )

                    _submit_prompt_and_save(
                        page,
                        context,
                        web_prompt,
                        out_png,
                        status_cb=lambda msg: status_cb(completed, total, msg),
                    )
                    on_scene_done(scene_num, out_png)
                    completed += 1
                    status_cb(
                        completed,
                        total,
                        f"Saved browser image for Scene {scene_num} ({completed}/{total})",
                    )
                    time.sleep(1.5)
            finally:
                context.close()
    finally:
        _BROWSER_LOCK.release()


def generate_single_image_via_browser(
    scene_index: int,
    scene_prompt: str,
    character_bible: str,
    output_path: Path,
) -> Path:
    if not _BROWSER_LOCK.acquire(blocking=False):
        raise BrowserImageError(
            "Another Gemini browser session is already active. Please wait for it to finish."
        )
    try:
        with sync_playwright() as pw:
            context = _launch_context(pw)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(GEMINI_WEB_URL, wait_until="domcontentloaded", timeout=45000)
                _wait_for_login(page)
                full_prompt = build_full_image_prompt(scene_prompt, character_bible)
                web_prompt = (
                    f"Generate a 16:9 widescreen image (no text, no words, no watermarks): "
                    f"{full_prompt}"
                )
                return _submit_prompt_and_save(page, context, web_prompt, output_path)
            finally:
                context.close()
    finally:
        _BROWSER_LOCK.release()
