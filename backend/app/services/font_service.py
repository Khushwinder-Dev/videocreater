import logging
import os
from pathlib import Path
from typing import Optional, Tuple

import httpx

from ..config import FONTS_DIR

logger = logging.getLogger(__name__)

NOTO_DEVANAGARI_URLS = {
    "NotoSansDevanagari-Regular.ttf": (
        "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/"
        "NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
    ),
    "NotoSansDevanagari-Bold.ttf": (
        "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/"
        "NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
    ),
}


def _find_system_font(candidates: list[str]) -> Optional[Path]:
    search_dirs = [
        FONTS_DIR,
        Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path.home() / "Library" / "Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
    ]
    for directory in search_dirs:
        if not directory.exists():
            continue
        for name in candidates:
            direct = directory / name
            if direct.exists():
                return direct
            # Shallow recursive match in font subfolders
            for match in directory.rglob(name):
                if match.is_file():
                    return match
    return None


def ensure_devanagari_font() -> Tuple[str, Optional[Path]]:
    """
    Ensures Noto Sans Devanagari is available locally for FFmpeg libass and Pillow.
    Returns (font_family_name, font_file_path).
    """
    local_bold = FONTS_DIR / "NotoSansDevanagari-Bold.ttf"
    local_reg = FONTS_DIR / "NotoSansDevanagari-Regular.ttf"

    if local_bold.exists() and local_bold.stat().st_size > 10_000:
        return ("Noto Sans Devanagari", local_bold)

    existing = _find_system_font(
        [
            "NotoSansDevanagari-Bold.ttf",
            "NotoSansDevanagari-Regular.ttf",
            "NotoSansDevanagari[wdth,wght].ttf",
        ]
    )
    if existing:
        return ("Noto Sans Devanagari", existing)

    # Attempt one-time download into backend/fonts/
    try:
        FONTS_DIR.mkdir(parents=True, exist_ok=True)
        url = NOTO_DEVANAGARI_URLS["NotoSansDevanagari-Bold.ttf"]
        logger.info("Downloading Noto Sans Devanagari font into %s...", FONTS_DIR)
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            local_bold.write_bytes(resp.content)
            if not local_reg.exists():
                local_reg.write_bytes(resp.content)
        return ("Noto Sans Devanagari", local_bold)
    except Exception as exc:
        logger.warning("Could not download Noto Sans Devanagari (%s). Falling back to OS font.", exc)

    fallback = _find_system_font(
        [
            "NirmalaB.ttf",
            "Nirmala.ttf",
            "Mangal.ttf",
            "KohinoorDevanagari.ttc",
            "DevanagariSangamMN.ttc",
        ]
    )
    if fallback:
        family = "Nirmala UI" if "Nirmala" in fallback.name else fallback.stem
        return (family, fallback)

    return ("Noto Sans Devanagari", None)


def ensure_latin_font() -> Tuple[str, Optional[Path]]:
    """
    Returns a clean bold sans-serif font for English subtitles and thumbnails.
    """
    font = _find_system_font(
        [
            "Inter-Bold.ttf",
            "Poppins-Bold.ttf",
            "Montserrat-Bold.ttf",
            "DejaVuSans-Bold.ttf",
            "arialbd.ttf",
            "Arial Bold.ttf",
            "HelveticaNeue.ttc",
            "segoeui.ttf",
            "segoeuib.ttf",
        ]
    )
    if font:
        name = font.stem
        if "arial" in name.lower():
            return ("Arial", font)
        if "segoe" in name.lower():
            return ("Segoe UI", font)
        if "dejavu" in name.lower():
            return ("DejaVu Sans", font)
        return (name, font)
    return ("Arial", None)
