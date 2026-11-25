import logging
import subprocess
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, features

from .font_service import ensure_devanagari_font, ensure_latin_font

logger = logging.getLogger(__name__)

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720


def _fit_cover_1280x720(src_img: Image.Image) -> Image.Image:
    src = src_img.convert("RGB")
    src_w, src_h = src.size
    target_ratio = THUMB_WIDTH / THUMB_HEIGHT
    src_ratio = src_w / max(1, src_h)

    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        src = src.crop((left, 0, left + new_w, src_h))
    elif src_ratio < target_ratio:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        src = src.crop((0, top, src_w, top + new_h))

    return src.resize((THUMB_WIDTH, THUMB_HEIGHT), Image.Resampling.LANCZOS)


def _apply_cinematic_vignette(img: Image.Image) -> Image.Image:
    # Subtle contrast & saturation boost for YouTube pop
    img = ImageEnhance.Color(img).enhance(1.18)
    img = ImageEnhance.Contrast(img).enhance(1.08)

    overlay = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Bottom gradient for bold text readability
    for y in range(THUMB_HEIGHT // 3, THUMB_HEIGHT):
        progress = (y - THUMB_HEIGHT // 3) / (THUMB_HEIGHT - THUMB_HEIGHT // 3)
        alpha = int(205 * (progress ** 1.35))
        draw.line([(0, y), (THUMB_WIDTH, y)], fill=(8, 10, 18, alpha))

    # Left dark edge vignette
    for x in range(0, THUMB_WIDTH // 2):
        progress = 1.0 - (x / (THUMB_WIDTH // 2))
        alpha = int(95 * (progress ** 1.6))
        draw.line([(x, 0), (x, THUMB_HEIGHT)], fill=(8, 10, 18, alpha))

    composed = Image.alpha_composite(img.convert("RGBA"), overlay)
    return composed.convert("RGB")


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 6:
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            pass
    return (255, 209, 102)


def _hex_to_ass_bgr(hex_color: str) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _escape_filter_path(p: Path) -> str:
    return str(p.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _render_hindi_text_via_ass(
    base_png: Path,
    overlay_text: str,
    accent_color: str,
    output_png: Path,
) -> None:
    """
    Uses FFmpeg libass + HarfBuzz + Noto Sans Devanagari to render crisp,
    properly shaped Devanagari bold thumbnail text when Pillow lacks libraqm.
    """
    font_family, font_file = ensure_devanagari_font()
    wrapped = "\\N".join(textwrap.wrap(overlay_text.strip(), width=20))
    ass_color = _hex_to_ass_bgr(accent_color)

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {THUMB_WIDTH}
PlayResY: {THUMB_HEIGHT}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Thumb,{font_family},94,{ass_color},&H00FFFFFF,&H00090B10,&HA0000000,-1,0,0,0,100,100,0,0,1,7,4,1,68,68,54,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Thumb,,0,0,0,,{wrapped}
"""
    ass_path = output_png.with_suffix(".thumb.ass")
    ass_path.write_text(ass_content, encoding="utf-8")

    esc_ass = _escape_filter_path(ass_path)
    if font_file:
        esc_fonts = _escape_filter_path(font_file.parent)
        vf = f"ass='{esc_ass}':fontsdir='{esc_fonts}'"
    else:
        vf = f"ass='{esc_ass}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(base_png),
        "-vf",
        vf,
        "-frames:v",
        "1",
        str(output_png),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    ass_path.unlink(missing_ok=True)
    if res.returncode != 0:
        raise RuntimeError(f"Thumbnail ASS text overlay failed: {res.stderr[-400:]}")


def _render_pillow_text(
    canvas: Image.Image,
    overlay_text: str,
    language: str,
    accent_color: str,
) -> Image.Image:
    if language == "hindi":
        _, font_path = ensure_devanagari_font()
    else:
        _, font_path = ensure_latin_font()

    font_size = 86
    try:
        if font_path and font_path.exists():
            font = ImageFont.truetype(str(font_path), font_size)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    lines = textwrap.wrap(overlay_text.strip(), width=18)
    if not lines:
        return canvas

    # Shadow layer
    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)

    line_height = int(font_size * 1.18)
    total_h = line_height * len(lines)
    y_start = THUMB_HEIGHT - total_h - 58
    x_pos = 64

    for idx, line in enumerate(lines):
        y = y_start + idx * line_height
        s_draw.text((x_pos + 5, y + 6), line, font=font, fill=(0, 0, 0, 210))

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=6))
    composed = Image.alpha_composite(canvas.convert("RGBA"), shadow_layer)

    draw = ImageDraw.Draw(composed)
    accent_rgb = _hex_to_rgb(accent_color)

    for idx, line in enumerate(lines):
        y = y_start + idx * line_height
        fill_color = accent_rgb if idx == 0 else (255, 255, 255)
        draw.text(
            (x_pos, y),
            line,
            font=font,
            fill=fill_color,
            stroke_width=7,
            stroke_fill=(12, 14, 22),
        )

    return composed.convert("RGB")


def create_thumbnail(
    background_image_path: Path,
    overlay_text: str,
    language: str,
    accent_color: str,
    output_path: Path,
) -> Path:
    """Create a 1280x720 YouTube thumbnail with Pillow framing and bold text overlay."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(background_image_path) as raw:
        canvas = _fit_cover_1280x720(raw)

    canvas = _apply_cinematic_vignette(canvas)

    # Subtle golden/white border accent
    draw = ImageDraw.Draw(canvas)
    accent_rgb = _hex_to_rgb(accent_color)
    draw.rectangle([(6, 6), (THUMB_WIDTH - 7, THUMB_HEIGHT - 7)], outline=accent_rgb, width=4)

    use_raqm = bool(features.check("raqm"))
    if language == "hindi" and not use_raqm:
        tmp_bg = output_path.with_suffix(".bg.png")
        canvas.save(tmp_bg, format="PNG")
        try:
            _render_hindi_text_via_ass(tmp_bg, overlay_text, accent_color, output_path)
        finally:
            tmp_bg.unlink(missing_ok=True)
    else:
        final_img = _render_pillow_text(canvas, overlay_text, language, accent_color)
        final_img.save(output_path, format="PNG")

    return output_path
