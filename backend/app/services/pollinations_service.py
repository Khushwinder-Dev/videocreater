import logging
import random
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

import httpx
from PIL import Image

from ..config import (
    ANIME_WATERCOLOR_STYLE,
    POLLINATIONS_API_KEY,
    POLLINATIONS_MODEL,
)
from .gemini_service import sanitize_image_prompt

logger = logging.getLogger(__name__)


class PollinationsServiceError(Exception):
    """User-friendly error raised when Pollinations image generation fails."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def build_compact_pollinations_prompt(scene_prompt: str, character_bible: str) -> str:
    """
    Build a concise, copyright-free 16:9 anime watercolor prompt within safe URL length.
    """
    safe_scene = sanitize_image_prompt(scene_prompt)
    safe_bible = sanitize_image_prompt(character_bible)

    if len(safe_bible) > 220:
        safe_bible = safe_bible[:217].rsplit(" ", 1)[0] + "..."
    if len(safe_scene) > 340:
        safe_scene = safe_scene[:337].rsplit(" ", 1)[0] + "..."

    parts = [safe_scene]
    if safe_bible:
        parts.append(f"Characters: {safe_bible}")
    parts.append(ANIME_WATERCOLOR_STYLE)
    combined = ". ".join(p.strip().rstrip(".") for p in parts if p.strip())
    return combined[:760]


def generate_image(
    scene_prompt: str,
    character_bible: str,
    output_path: Path,
    seed: Optional[int] = None,
    model: Optional[str] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> Path:
    """
    Generate a 1280x720 (16:9) PNG using Pollinations.ai (`image.pollinations.ai`,
    or `gen.pollinations.ai` when POLLINATIONS_API_KEY is set).
    Automatically honors Pollinations anonymous IP cooldowns (`402 FREE_LIMIT`).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = build_compact_pollinations_prompt(scene_prompt, character_bible)
    encoded_prompt = quote(prompt, safe="")
    chosen_model = (model or POLLINATIONS_MODEL or "flux").strip()
    chosen_seed = seed if seed is not None else random.randint(1, 999999)

    if POLLINATIONS_API_KEY:
        url = (
            f"https://gen.pollinations.ai/image/{encoded_prompt}"
            f"?width=1280&height=720&model={quote(chosen_model)}&nologo=true&seed={chosen_seed}"
        )
        headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}
    else:
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width=1280&height=720&model={quote(chosen_model)}&nologo=true&seed={chosen_seed}"
        )
        headers = {}

    last_err: Optional[str] = None
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=75.0, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)

            if resp.status_code == 200:
                ctype = (resp.headers.get("content-type") or "").lower()
                if "image" not in ctype and len(resp.content) < 5000:
                    raise PollinationsServiceError(
                        f"Unexpected non-image response from Pollinations: {resp.text[:200]}"
                    )
                with Image.open(BytesIO(resp.content)) as img:
                    rgb = img.convert("RGB")
                    if rgb.size != (1280, 720):
                        rgb = rgb.resize((1280, 720), Image.Resampling.LANCZOS)
                    rgb.save(output_path, format="PNG")
                time.sleep(1.0)
                return output_path

            last_err = f"HTTP {resp.status_code}: {resp.text[:240]}"
            is_free_limit = resp.status_code == 402 and (
                "free_limit" in resp.text.lower() or "retry after" in resp.text.lower()
            )
            if is_free_limit and attempt < max_attempts:
                m = re.search(r"retry after\s+(\d+)\s*s", resp.text, re.IGNORECASE)
                wait_sec = (int(m.group(1)) + 2) if m else 47
                wait_sec = min(60, max(5, wait_sec))
                msg = (
                    f"Pollinations free tier allows 1 image per 45s. Waiting {wait_sec}s for {output_path.name} "
                    f"(add POLLINATIONS_API_KEY in .env for instant batches)..."
                )
                logger.info(msg)
                if status_cb:
                    status_cb(msg)
                time.sleep(wait_sec)
                continue

            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                backoff = (2 ** (attempt - 1)) * 2.5 + random.uniform(0.3, 1.0)
                logger.warning(
                    "Pollinations returned %s (attempt %d/%d). Retrying in %.1fs...",
                    resp.status_code,
                    attempt,
                    max_attempts,
                    backoff,
                )
                time.sleep(backoff)
                continue
            break
        except PollinationsServiceError:
            raise
        except Exception as exc:
            last_err = str(exc)
            if attempt < max_attempts:
                backoff = (2 ** (attempt - 1)) * 2.5 + random.uniform(0.3, 1.0)
                logger.warning(
                    "Pollinations request failed (%s, attempt %d/%d). Retrying in %.1fs...",
                    exc,
                    attempt,
                    max_attempts,
                    backoff,
                )
                time.sleep(backoff)
                continue
            break

    raise PollinationsServiceError(
        f"Pollinations image generation failed for {output_path.name}: {last_err or 'Unknown error'}",
        status_code=502,
    )
