import base64
import hashlib
import logging
import os
import re
import socket
import subprocess
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from PIL import Image

from ..config import (
    FASTSD_DIR,
    FASTSD_GUIDANCE,
    FASTSD_STEPS,
    FASTSD_URL,
    LOCAL_NEGATIVE_PROMPT,
    LOCAL_STYLE_PREFIX,
    PROJECTS_DIR,
    ROOT_DIR,
    UPSCALE_ENABLED,
    UPSCAYL_BIN,
)
from .gemini_service import rewrite_prompt_for_sd15, sanitize_image_prompt

logger = logging.getLogger(__name__)

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
GEN_WIDTH = 640
GEN_HEIGHT = 360

_FASTSD_START_LOCK = threading.Lock()
_FASTSD_GEN_LOCK = threading.Lock()
_FASTSD_PROC: Optional[subprocess.Popen] = None


class LocalImageServiceError(Exception):
    """User-friendly error raised by the FastSD CPU / Real-ESRGAN local image pipeline."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def resolve_tool_path(raw_path: str) -> Path:
    cleaned = raw_path.strip().strip('"')
    p = Path(cleaned)
    if not p.is_absolute():
        p = (ROOT_DIR / p).resolve()
    return p


def _extract_character_tokens(character_bible: str) -> List[str]:
    """Extract likely character names from the Character Bible for per-group seed locking."""
    if not character_bible.strip():
        return []
    stop_words = {
        "The", "A", "An", "In", "On", "At", "He", "She", "They", "His", "Her",
        "Their", "With", "Wearing", "Hair", "Eyes", "World", "Palette", "Style",
        "Setting", "Warm", "Soft", "Young", "Old", "Little", "Wise", "Kind",
        "Village", "Forest", "Story", "Characters", "Character", "Scene",
    }
    candidates = re.findall(r"\b[A-Z][a-z]{2,20}\b", character_bible)
    unique: List[str] = []
    for name in candidates:
        if name not in stop_words and name not in unique:
            unique.append(name)
    return unique


def compute_character_group_seed(scene_prompt: str, character_bible: str) -> int:
    """
    Returns one deterministic seed per character group so characters keep consistent
    traits across scenes featuring the same cast.
    """
    names = _extract_character_tokens(character_bible)
    lower_prompt = scene_prompt.lower()
    present = sorted({n for n in names if re.search(rf"\b{re.escape(n.lower())}\b", lower_prompt)})
    group_key = "|".join(present) if present else (character_bible.strip() or "default_cast")
    digest = hashlib.sha256(group_key.encode("utf-8")).hexdigest()[:8]
    return 100_000 + (int(digest, 16) % 2_000_000_000)


def build_local_sd_prompt(compact_scene_prompt: str) -> str:
    clean_scene = sanitize_image_prompt(compact_scene_prompt).strip().rstrip(".")
    # Truncate overly long descriptions so all tokens stay within CLIP's 77-token budget
    words = clean_scene.split()
    if len(words) > 38:
        clean_scene = " ".join(words[:38])
    # Lock 2D anime style in the very first tokens (prevents photorealistic faces on DreamShaper-8)
    return (
        f"2d anime illustration, cel-shaded, hand-painted anime watercolor, soft pastel colors, "
        f"{clean_scene}, detailed anime face, clear expressive eyes, "
        f"warm golden light, detailed painterly background"
    )


def _is_tcp_port_open(fastsd_url: str, timeout: float = 0.8) -> bool:
    """Return True if the FastSD host:port TCP socket is accepting connections (even if busy rendering)."""
    try:
        parsed = urlparse(fastsd_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_fastsd_http_ready(fastsd_url: str, timeout: float = 2.5) -> bool:
    if not _is_tcp_port_open(fastsd_url, timeout=0.8):
        return False
    for endpoint in ("/api/info", "/api/config", "/api/docs"):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(f"{fastsd_url}{endpoint}")
            if resp.status_code < 500:
                return True
        except Exception:
            continue
    return False


def _is_fastsd_reachable(fastsd_url: str, timeout: float = 2.5) -> bool:
    if _is_fastsd_http_ready(fastsd_url, timeout=timeout):
        return True
    # FastSD CPU handles /api/generate synchronously on one Uvicorn worker; if the TCP
    # port is open, FastSD CPU is alive (busy generating) and must not be re-launched.
    return _is_tcp_port_open(fastsd_url, timeout=0.8)


def ensure_fastsd_running(
    settings: Optional[Dict[str, Any]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
    wait_timeout_sec: int = 240,
) -> bool:
    """
    Checks if FastSD CPU is reachable; if not, attempts to start it automatically
    from ./tools/fastsdcpu as a background subprocess and waits until it responds.
    """
    global _FASTSD_PROC
    cfg = settings or {}
    fastsd_url = str(cfg.get("fastsd_url") or FASTSD_URL).strip().rstrip("/")
    if _is_fastsd_reachable(fastsd_url):
        return True

    with _FASTSD_START_LOCK:
        if _is_fastsd_reachable(fastsd_url):
            return True

        app_py = FASTSD_DIR / "src" / "app.py"
        if not app_py.exists():
            return False

        if os.name == "nt":
            py_exe = FASTSD_DIR / "env" / "Scripts" / "python.exe"
            openvino_libs = FASTSD_DIR / "env" / "Lib" / "site-packages" / "openvino" / "libs"
        else:
            py_exe = FASTSD_DIR / "env" / "bin" / "python"
            openvino_libs = None

        if not py_exe.exists():
            logger.warning("FastSD CPU venv python not found at %s", py_exe)
            return False

        if status_cb:
            status_cb("FastSD CPU is offline — starting local FastSD CPU server automatically...")

        env = os.environ.copy()
        if openvino_libs and openvino_libs.exists():
            env["PATH"] = f"{openvino_libs};{env.get('PATH', '')}"
        hf_cache_dir = ROOT_DIR / "tools" / ".cache" / "huggingface"
        hf_cache_dir.mkdir(parents=True, exist_ok=True)
        env.setdefault("HF_HOME", str(hf_cache_dir))
        env.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_cache_dir / "hub"))
        env.setdefault("PYTHONUNBUFFERED", "1")

        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = PROJECTS_DIR / "fastsdcpu.log"
        log_file = open(log_path, "ab")

        popen_kwargs: Dict[str, Any] = {
            "cwd": str(FASTSD_DIR),
            "env": env,
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

        if _FASTSD_PROC is None or _FASTSD_PROC.poll() is not None:
            logger.info("Auto-starting FastSD CPU API server from %s...", FASTSD_DIR)
            _FASTSD_PROC = subprocess.Popen(
                [str(py_exe), "-u", str(app_py), "--api"],
                **popen_kwargs,
            )

        deadline = time.time() + wait_timeout_sec
        while time.time() < deadline:
            if _is_fastsd_reachable(fastsd_url, timeout=2.0):
                logger.info("FastSD CPU is now reachable at %s", fastsd_url)
                return True
            if _FASTSD_PROC and _FASTSD_PROC.poll() is not None:
                logger.error("FastSD CPU process exited early (code %s). See %s", _FASTSD_PROC.returncode, log_path)
                break
            time.sleep(2.0)

        return _is_fastsd_reachable(fastsd_url)


def _resolve_upscayl_binary_and_model(upscayl_bin_str: str) -> Tuple[Optional[Path], Optional[Path], Optional[str]]:
    """
    Locate Real-ESRGAN / upscayl-bin executable, its bundled models folder,
    and preferred anime/standard model.
    """
    candidates: List[Path] = []
    if upscayl_bin_str:
        candidates.append(resolve_tool_path(upscayl_bin_str))
    # Automatic fallback to portable ./tools/upscayl binary if installed by setup_local
    exe_name = "realesrgan-ncnn-vulkan.exe" if os.name == "nt" else "realesrgan-ncnn-vulkan"
    candidates.append(ROOT_DIR / "tools" / "upscayl" / exe_name)

    bin_path: Optional[Path] = None
    for cand in candidates:
        if cand.exists() and cand.is_file():
            bin_path = cand
            break

    if not bin_path:
        return (candidates[0] if candidates else None), None, None

    models_dir: Optional[Path] = None
    for candidate in (
        bin_path.parent / "models",
        bin_path.parent.parent / "models",
        bin_path.parent.parent / "resources" / "models",
    ):
        if candidate.exists() and candidate.is_dir():
            models_dir = candidate
            break

    chosen_model: Optional[str] = None
    if models_dir:
        available = {p.stem for p in models_dir.glob("*.param")}
        for preferred in (
            "realesrgan-x4plus-anime",
            "upscayl-standard-4x",
            "realesrgan-x4plus",
            "ultramix-balanced-4x",
        ):
            if preferred in available:
                chosen_model = preferred
                break
        if not chosen_model and available:
            chosen_model = sorted(available)[0]

    return bin_path, models_dir, chosen_model


def check_services(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Confirm FastSD CPU API is reachable and Real-ESRGAN/Upscayl binary exists (if enabled).
    Returns structured status and clear actionable errors.
    """
    cfg = settings or {}
    fastsd_url = str(cfg.get("fastsd_url") or FASTSD_URL).strip().rstrip("/")
    upscayl_bin_str = str(cfg.get("upscayl_bin") or UPSCAYL_BIN).strip()
    upscale_enabled = bool(cfg.get("upscale_enabled", UPSCALE_ENABLED))

    errors: List[str] = []
    http_ok = _is_fastsd_http_ready(fastsd_url)
    fastsd_ok = http_ok or _is_tcp_port_open(fastsd_url)
    auto_start_available = (FASTSD_DIR / "src" / "app.py").exists()

    if http_ok:
        fastsd_msg = f"FastSD CPU reachable at {fastsd_url}"
    elif fastsd_ok:
        fastsd_msg = f"FastSD CPU is busy generating an image at {fastsd_url}"
    elif auto_start_available:
        fastsd_msg = (
            f"FastSD CPU is offline at {fastsd_url} (will auto-start from ./tools/fastsdcpu when generating)."
        )
    else:
        fastsd_msg = (
            f"FastSD CPU API is not reachable at {fastsd_url}. "
            f"Run setup_local.bat / setup_local.sh or start it with: python src/app.py --api"
        )
        errors.append(fastsd_msg)

    upscayl_ok = True
    upscayl_model = ""
    upscayl_msg = "Upscaling disabled in Settings"

    if upscale_enabled:
        bin_path, models_dir, chosen_model = _resolve_upscayl_binary_and_model(upscayl_bin_str)
        if not bin_path or not bin_path.exists():
            upscayl_ok = False
            upscayl_msg = (
                f"Upscaler binary not found at: {upscayl_bin_str or '(not set)'}. "
                f"Run setup_local.bat / setup_local.sh (installs ./tools/upscayl/) or disable Upscaling in Settings."
            )
            errors.append(upscayl_msg)
        elif not models_dir or not chosen_model:
            upscayl_ok = False
            upscayl_msg = (
                f"Found {bin_path.name}, but no .param/.bin models were found in {bin_path.parent / 'models'}."
            )
            errors.append(upscayl_msg)
        else:
            upscayl_ok = True
            upscayl_model = chosen_model
            upscayl_msg = f"Upscaler ready ({bin_path.name}, model: {chosen_model})"

    return {
        "ok": (fastsd_ok or auto_start_available) and upscayl_ok,
        "fastsd_ok": fastsd_ok,
        "auto_start_available": auto_start_available,
        "fastsd_message": fastsd_msg,
        "upscayl_ok": upscayl_ok,
        "upscayl_model": upscayl_model,
        "upscayl_message": upscayl_msg,
        "errors": errors,
    }


def _fit_1920x1080_lanczos(src_path: Path, out_path: Path) -> Path:
    """Center-crop to 16:9 if needed and resize cleanly to 1920x1080 using Pillow LANCZOS."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src_path) as img:
        rgb = img.convert("RGB")
        w, h = rgb.size
        target_ratio = TARGET_WIDTH / TARGET_HEIGHT
        cur_ratio = w / max(1, h)

        if cur_ratio > target_ratio + 0.01:
            new_w = int(round(h * target_ratio))
            left = max(0, (w - new_w) // 2)
            rgb = rgb.crop((left, 0, left + new_w, h))
        elif cur_ratio < target_ratio - 0.01:
            new_h = int(round(w / target_ratio))
            top = max(0, (h - new_h) // 2)
            rgb = rgb.crop((0, top, w, top + new_h))

        if rgb.size != (TARGET_WIDTH, TARGET_HEIGHT):
            rgb = rgb.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        rgb.save(out_path, format="PNG")
    return out_path


def generate_image(
    prompt: str,
    negative_prompt: str,
    seed: int,
    out_path: Path,
    settings: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Generate a 640x360 (16:9) base image via FastSD CPU API (`POST /api/generate`)
    using SD 1.5 + LCM-LoRA + full SD 1.5 VAE (cleaner faces than TAESD). Retries 3 times.
    """
    cfg = settings or {}
    fastsd_url = str(cfg.get("fastsd_url") or FASTSD_URL).strip().rstrip("/")
    steps = max(4, min(6, int(cfg.get("steps") or FASTSD_STEPS)))
    guidance = max(1.0, min(1.5, float(cfg.get("guidance_scale") or FASTSD_GUIDANCE)))

    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "diffusion_task": "text_to_image",
        "prompt": prompt,
        "negative_prompt": negative_prompt or LOCAL_NEGATIVE_PROMPT,
        "image_width": GEN_WIDTH,
        "image_height": GEN_HEIGHT,
        "inference_steps": steps,
        "guidance_scale": guidance,
        "seed": int(seed),
        "use_seed": True,
        "number_of_images": 1,
        "use_lcm_lora": True,
        "use_tiny_auto_encoder": False,
        "use_openvino": False,
        "use_safety_checker": False,
        "lcm_lora": {
            "base_model_id": "Lykon/dreamshaper-8",
            "lcm_lora_id": "latent-consistency/lcm-lora-sdv1-5",
        },
    }

    last_err: Optional[str] = None
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            with _FASTSD_GEN_LOCK:
                with httpx.Client(timeout=1800.0) as client:
                    resp = client.post(f"{fastsd_url}/api/generate", json=payload)

            if resp.status_code == 200:
                data = resp.json()
                b64_img = None
                if isinstance(data.get("images"), list) and data["images"]:
                    b64_img = data["images"][0]
                elif isinstance(data.get("image"), str):
                    b64_img = data["image"]

                if not b64_img:
                    raise LocalImageServiceError(
                        f"FastSD CPU returned 200 OK without image data: {list(data.keys())}"
                    )

                if "," in b64_img and b64_img.startswith("data:"):
                    b64_img = b64_img.split(",", 1)[1]

                raw_bytes = base64.b64decode(b64_img)
                with Image.open(BytesIO(raw_bytes)) as img:
                    img.convert("RGB").save(out_path, format="PNG")
                return out_path

            last_err = f"HTTP {resp.status_code}: {resp.text[:250]}"
        except LocalImageServiceError:
            raise
        except Exception as exc:
            last_err = str(exc)

        if attempt < max_attempts:
            backoff = 1.5 * (2 ** (attempt - 1))
            logger.warning(
                "FastSD CPU generation failed (attempt %d/%d): %s. Retrying in %.1fs...",
                attempt,
                max_attempts,
                last_err,
                backoff,
            )
            time.sleep(backoff)

    raise LocalImageServiceError(
        f"FastSD CPU generation failed at {fastsd_url}/api/generate after {max_attempts} attempts: {last_err}",
        status_code=502,
    )


def upscale_image(
    in_path: Path,
    out_path: Path,
    settings: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, Optional[str]]:
    """
    Upscale in_path 4x using Real-ESRGAN / Upscayl CLI, then fit cleanly to 1920x1080.
    If upscaler is missing or fails (e.g. Vulkan not supported), falls back to plain
    Pillow LANCZOS resize and returns a warning message.
    """
    cfg = settings or {}
    upscale_enabled = bool(cfg.get("upscale_enabled", UPSCALE_ENABLED))
    upscayl_bin_str = str(cfg.get("upscayl_bin") or UPSCAYL_BIN).strip()

    if not upscale_enabled:
        return _fit_1920x1080_lanczos(in_path, out_path), None

    bin_path, models_dir, chosen_model = _resolve_upscayl_binary_and_model(upscayl_bin_str)
    if not bin_path or not bin_path.exists() or not models_dir or not chosen_model:
        warn = (
            f"Upscaler binary/models unavailable ({upscayl_bin_str}); "
            "fell back to Pillow LANCZOS resize to 1920x1080."
        )
        logger.warning(warn)
        return _fit_1920x1080_lanczos(in_path, out_path), warn

    tmp_upscaled = out_path.with_suffix(".upscaled.png")
    tmp_upscaled.parent.mkdir(parents=True, exist_ok=True)

    bin_dir = bin_path.parent
    models_arg = "models" if models_dir == (bin_dir / "models") else str(models_dir)

    cmd = [
        str(bin_path),
        "-i",
        str(in_path.resolve()),
        "-o",
        str(tmp_upscaled.resolve()),
        "-m",
        models_arg,
        "-n",
        chosen_model,
        "-s",
        "4",
        "-f",
        "png",
    ]
    res = subprocess.run(cmd, cwd=str(bin_dir), capture_output=True, text=True, check=False)
    if res.returncode != 0 or not tmp_upscaled.exists():
        err_tail = ((res.stderr or "") + " " + (res.stdout or "")).strip()[-240:]
        tmp_upscaled.unlink(missing_ok=True)
        warn = (
            f"Real-ESRGAN/Upscayl failed (Vulkan unsupported or GPU/memory error: {err_tail}); "
            "fell back to Pillow LANCZOS resize to 1920x1080."
        )
        logger.warning(warn)
        return _fit_1920x1080_lanczos(in_path, out_path), warn

    try:
        return _fit_1920x1080_lanczos(tmp_upscaled, out_path), None
    finally:
        tmp_upscaled.unlink(missing_ok=True)


def generate_and_upscale_scene(
    scene_prompt: str,
    character_bible: str,
    out_path: Path,
    seed: Optional[int] = None,
    settings: Optional[Dict[str, Any]] = None,
    stage_cb: Optional[Callable[[str], None]] = None,
    status_msg_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[Path, int, Optional[str]]:
    """
    Full local pipeline for one image:
      1) Ensure FastSD CPU is running (auto-starts from ./tools/fastsdcpu if offline)
      2) Rewrite prompt under 60 words for SD 1.5 + prepend style string
      3) Compute fixed character-group seed (if seed not supplied)
      4) Generate 512x288 via FastSD CPU
      5) Upscale 4x via Real-ESRGAN/Upscayl CLI (with Pillow LANCZOS fallback) -> 1920x1080
    Returns (final_out_path, seed_used, upscale_warning).
    """
    if not ensure_fastsd_running(settings=settings, status_cb=status_msg_cb):
        fastsd_url = str((settings or {}).get("fastsd_url") or FASTSD_URL).strip()
        raise LocalImageServiceError(
            f"FastSD CPU is not reachable at {fastsd_url} and could not auto-start. "
            f"Run setup_local.bat / setup_local.sh or start FastSD CPU manually.",
            status_code=502,
        )

    used_seed = seed if seed is not None else compute_character_group_seed(scene_prompt, character_bible)
    compact = rewrite_prompt_for_sd15(scene_prompt, character_bible)
    full_prompt = build_local_sd_prompt(compact)

    raw_path = out_path.with_suffix(".raw512.png")
    try:
        if stage_cb:
            stage_cb("generating")
        generate_image(
            prompt=full_prompt,
            negative_prompt=LOCAL_NEGATIVE_PROMPT,
            seed=used_seed,
            out_path=raw_path,
            settings=settings,
        )

        if stage_cb:
            stage_cb("upscaling")
        final_path, warning = upscale_image(raw_path, out_path, settings=settings)
        return final_path, used_seed, warning
    finally:
        raw_path.unlink(missing_ok=True)
