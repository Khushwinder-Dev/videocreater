import json
import logging
import random
import re
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image, ImageDraw

from ..config import (
    ANIME_WATERCOLOR_STYLE,
    COPYRIGHTED_TERMS,
    GEMINI_API_KEY,
    GEMINI_API_KEYS,
    GEMINI_IMAGE_FALLBACK_MODELS,
    GEMINI_IMAGE_MODEL,
    GEMINI_MAX_RETRIES,
    GEMINI_REQUEST_DELAY_SEC,
    GEMINI_TEXT_FALLBACK_MODELS,
    GEMINI_TEXT_MODEL,
    GENRE_LABELS,
)
from ..models import SceneBreakdownResponse, SceneItem, TopicsListResponse, YouTubePackageModel

logger = logging.getLogger(__name__)
T = TypeVar("T")
_KEY_LOCK = threading.Lock()
_KEY_INDEX = 0
_CLIENT_CACHE: Dict[tuple[str, Optional[str]], genai.Client] = {}


class GeminiServiceError(Exception):
    """User-friendly exception raised when Gemini calls fail after retries."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _current_api_key() -> str:
    keys = GEMINI_API_KEYS or ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
    if not keys:
        return ""
    with _KEY_LOCK:
        return keys[_KEY_INDEX % len(keys)]


def rotate_gemini_key() -> bool:
    """Advance to the next configured Gemini API key. Returns True if multiple keys exist."""
    global _KEY_INDEX
    if len(GEMINI_API_KEYS) <= 1:
        return False
    with _KEY_LOCK:
        _KEY_INDEX = (_KEY_INDEX + 1) % len(GEMINI_API_KEYS)
        idx = _KEY_INDEX + 1
    logger.info("Rotated to Gemini API key #%d/%d.", idx, len(GEMINI_API_KEYS))
    return True


def get_gemini_client(api_version: Optional[str] = None, api_key: Optional[str] = None) -> genai.Client:
    chosen_key = api_key or _current_api_key()
    if not chosen_key or chosen_key == "your_gemini_api_key_here":
        raise GeminiServiceError(
            "GEMINI_API_KEY is missing. Please add one or more comma-separated Gemini API keys to .env and restart the backend.",
            status_code=400,
        )
    cache_key = (chosen_key, api_version)
    with _KEY_LOCK:
        cached = _CLIENT_CACHE.get(cache_key)
        if cached is not None:
            return cached
        opts: Dict[str, Any] = {"timeout": 120000}
        if api_version:
            opts["api_version"] = api_version
        client = genai.Client(api_key=chosen_key, http_options=opts)
        _CLIENT_CACHE[cache_key] = client
        return client


def _is_hard_quota_exhausted(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "limit: 0" in msg
        or "perday" in msg
        or "free_tier" in msg and "429" in msg and "perminute" not in msg
    )


def _is_retryable_error(exc: Exception) -> bool:
    if _is_hard_quota_exhausted(exc):
        return False
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        if code in (429, 500, 502, 503, 504):
            return True
    msg = str(exc).lower()
    retry_markers = (
        "429",
        "resource_exhausted",
        "quota",
        "rate limit",
        "too many requests",
        "503",
        "500",
        "unavailable",
        "deadline",
        "timeout",
        "temporarily",
    )
    return any(m in msg for m in retry_markers)


def _should_rotate_key_on_error(exc: Exception) -> bool:
    if len(GEMINI_API_KEYS) <= 1:
        return False
    msg = str(exc).lower()
    return any(
        m in msg
        for m in (
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "too many requests",
            "503",
            "unavailable",
            "504",
            "deadline",
        )
    )


def with_gemini_retry(
    fn: Callable[[], T],
    operation_name: str = "Gemini API call",
    max_attempts: Optional[int] = None,
) -> T:
    base_attempts = max_attempts or GEMINI_MAX_RETRIES
    total_keys = max(1, len(GEMINI_API_KEYS))
    attempts = max(base_attempts, total_keys) if total_keys > 1 else base_attempts
    rotations_used = 0
    last_exc: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except GeminiServiceError:
            raise
        except Exception as exc:
            last_exc = exc
            if _should_rotate_key_on_error(exc) and rotations_used < (total_keys - 1) and attempt < attempts:
                rotations_used += 1
                rotate_gemini_key()
                logger.warning(
                    "%s hit limit/capacity on current key (%s). Switching key (%d/%d)...",
                    operation_name,
                    exc,
                    rotations_used + 1,
                    total_keys,
                )
                time.sleep(0.2)
                continue

            if not _is_retryable_error(exc) or attempt == attempts:
                break
            backoff = min(15.0, (2 ** (attempt - 1)) * 1.2 + random.uniform(0.2, 0.8))
            logger.warning(
                "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                operation_name,
                attempt,
                attempts,
                exc,
                backoff,
            )
            time.sleep(backoff)

    err_text = str(last_exc) if last_exc else "Unknown Gemini error"
    lower = err_text.lower()
    if "429" in lower or "resource_exhausted" in lower or "quota" in lower:
        raise GeminiServiceError(
            f"Gemini API rate limit or quota exceeded during {operation_name}. Please wait a moment or check your Google AI Studio plan. Details: {err_text}",
            status_code=429,
        )
    if "401" in lower or "403" in lower or "api key" in lower or "permission" in lower:
        raise GeminiServiceError(
            f"Gemini API authentication failed during {operation_name}. Verify GEMINI_API_KEY in .env. Details: {err_text}",
            status_code=401,
        )
    raise GeminiServiceError(f"{operation_name} failed: {err_text}", status_code=502)


def _call_text_models_with_fallback(
    make_call: Callable[[str], T],
    operation_name: str,
) -> T:
    last_err: Optional[GeminiServiceError] = None
    total_models = len(GEMINI_TEXT_FALLBACK_MODELS)
    for idx, model_name in enumerate(GEMINI_TEXT_FALLBACK_MODELS):
        is_last = idx == total_models - 1
        try:
            return with_gemini_retry(
                lambda m=model_name: make_call(m),
                f"{operation_name} ({model_name})",
                max_attempts=GEMINI_MAX_RETRIES if is_last else 2,
            )
        except GeminiServiceError as exc:
            last_err = exc
            if exc.status_code == 401:
                raise
            logger.warning("Model %s failed for %s: %s. Trying fallback...", model_name, operation_name, exc.message)
    assert last_err is not None
    raise last_err


def sanitize_image_prompt(prompt: str) -> str:
    cleaned = prompt.strip()
    for term in COPYRIGHTED_TERMS:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        cleaned = pattern.sub("whimsical original", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def build_full_image_prompt(scene_prompt: str, character_bible: str) -> str:
    safe_scene = sanitize_image_prompt(scene_prompt)
    safe_bible = sanitize_image_prompt(character_bible)
    parts = []
    if safe_bible:
        parts.append(f"Consistent Character Reference: {safe_bible}.")
    parts.append(f"Scene: {safe_scene}.")
    parts.append(f"Art Style: {ANIME_WATERCOLOR_STYLE}.")
    return " ".join(parts)


def generate_topics(
    language: str,
    genre: str,
    target_length_min: int,
    target_duration_sec: Optional[int] = None,
) -> List[Dict[str, str]]:
    client = get_gemini_client()
    lang_name = "Hindi (Devanagari script)" if language == "hindi" else "English"
    genre_label = GENRE_LABELS.get(genre, genre)
    dur_sec = target_duration_sec if target_duration_sec is not None else target_length_min * 60
    duration_label = f"{dur_sec}-second quick test micro-story" if dur_sec <= 30 else f"{target_length_min}-minute"

    prompt = f"""
You are an expert YouTube storyteller and viral content strategist.
Generate 10 trending, original, emotionally compelling story topics for a {duration_label} YouTube story video.

Language: {lang_name}
Genre: {genre_label}

Requirements:
- All 10 topics must be completely original (no copyrighted characters, brands, or existing movies/shows).
- Write both the `title` and `hook` in {lang_name}.
- Each `title` should be intriguing and YouTube-friendly.
- Each `hook` must be a punchy 1-line curiosity hook that makes viewers click immediately.
- Return valid JSON matching the schema.
"""

    def _call(model_name: str):
        resp = get_gemini_client().models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TopicsListResponse,
                temperature=0.95,
            ),
        )
        parsed = TopicsListResponse.model_validate_json(resp.text)
        return [t.model_dump() for t in parsed.topics[:10]]

    return _call_text_models_with_fallback(_call, "Topic generation")


def generate_script(
    language: str,
    genre: str,
    target_length_min: int,
    topic: str,
    hook: str,
    target_duration_sec: Optional[int] = None,
) -> str:
    client = get_gemini_client()
    lang_name = "Hindi (written naturally in Devanagari script)" if language == "hindi" else "English"
    genre_label = GENRE_LABELS.get(genre, genre)
    dur_sec = target_duration_sec if target_duration_sec is not None else target_length_min * 60
    is_test_mode = dur_sec <= 30

    # 10 min default = ~1400 English words / ~1300 Hindi words
    base_words = 1300 if language == "hindi" else 1400
    if is_test_mode:
        target_words = max(25, int(round(base_words * (dur_sec / 600.0))))
        duration_desc = f"{dur_sec} seconds (quick test mode)"
        structure_note = (
            "Keep the story tight and complete in 3-4 crisp sentences: "
            "a 1-sentence hook, a brief turning point, an emotional ending, and a 1-line moral."
        )
    else:
        target_words = max(250, int(round(base_words * (dur_sec / 600.0))))
        duration_desc = f"{target_length_min} minutes"
        structure_note = """Story Structure Requirements:
1. **Hook (first 20-30 seconds)**: Start immediately with a dramatic, emotional, or curiosity-sparking opening line that pulls the listener in.
2. **Act 1 (Setup)**: Introduce the original characters, vivid setting, and initial conflict/desire.
3. **Act 2 (Rising Action & Turning Point)**: Build tension, unexpected twists, trials, or emotional stakes.
4. **Act 3 (Climax & Emotional Ending)**: Deliver a heartfelt, unforgettable climax and satisfying resolution.
5. **Closing Moral**: Conclude with a memorable, resonant moral or life reflection."""

    prompt = f"""
You are an acclaimed YouTube narrator and storywriter.
Write a complete, deeply engaging voiceover narration script in {lang_name}.

Topic: {topic}
Opening Hook Inspiration: {hook}
Genre: {genre_label}
Target Duration: {duration_desc}
Target Word Count: approximately {target_words} words (strictly aim near {target_words} words so the narration lasts ~{duration_desc} at a calm storytelling pace).

{structure_note}

Formatting Rules:
- Write ONLY pure spoken narration text suitable for direct text-to-speech voiceover.
- Do NOT include stage directions, camera notes, brackets like [music], speaker labels, or markdown headings/bullet points.
- Use natural paragraph breaks and expressive punctuation for pacing.
- Ensure all character names and world details are 100% original (no copyrighted names).
"""

    def _call(model_name: str):
        resp = get_gemini_client().models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.85,
                max_output_tokens=8192,
            ),
        )
        text = (resp.text or "").strip()
        if not text:
            raise ValueError("Gemini returned an empty script.")
        return text

    return _call_text_models_with_fallback(_call, "Script generation")


def generate_scenes(
    language: str,
    genre: str,
    target_length_min: int,
    script: str,
    target_duration_sec: Optional[int] = None,
) -> Dict[str, Any]:
    client = get_gemini_client()
    lang_name = "Hindi (Devanagari script)" if language == "hindi" else "English"
    dur_sec = target_duration_sec if target_duration_sec is not None else target_length_min * 60

    if dur_sec <= 30:
        min_scenes = 2
        max_scenes = 3
        target_scenes = 3
        pace_note = "each ~5-7 seconds when spoken (roughly 10-15 words per scene)"
    else:
        # For default 10 min: 60-75 scenes (~8-10 seconds each)
        min_scenes = max(12, int(round(60 * (dur_sec / 600.0))))
        max_scenes = max(min_scenes + 5, int(round(75 * (dur_sec / 600.0))))
        target_scenes = (min_scenes + max_scenes) // 2
        pace_note = "each ~8-10 seconds when spoken (roughly 15-25 words per scene)"

    prompt = f"""
You are a storyboard director adapting a voiceover script into visual scenes.

Language of Narration: {lang_name}
Genre: {GENRE_LABELS.get(genre, genre)}
Target Scene Count: between {min_scenes} and {max_scenes} scenes (aim for ~{target_scenes} scenes, {pace_note}).

Tasks:
1. Create a concise, detailed `character_bible` (in English) describing EVERY recurring character's exact visual appearance (age, facial features, hairstyle/color, clothing colors/fabrics, signature accessories) and the overarching world palette so all scenes look visually consistent.
2. Split the ENTIRE script verbatim (preserving the original {lang_name} wording without dropping sentences) into {min_scenes} to {max_scenes} sequential scenes.
3. For each scene, provide:
   - `scene_index`: 1-based integer (1, 2, 3...)
   - `narration`: the exact spoken lines for that scene in {lang_name} (roughly 15-25 words per scene).
   - `image_prompt`: a vivid, descriptive English visual prompt depicting that exact moment, referencing the characters by name and appearance from the character bible (e.g., camera framing, action, lighting, setting).
4. CRITICAL: Do NOT include ANY copyrighted studio, anime, movie, or character names (no Ghibli, Miyazaki, Disney, Pixar, etc.) in `character_bible` or `image_prompt`.

SCRIPT:
\"\"\"
{script}
\"\"\"
"""

    def _call(model_name: str):
        resp = get_gemini_client().models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SceneBreakdownResponse,
                temperature=0.45,
                max_output_tokens=16384,
            ),
        )
        parsed = SceneBreakdownResponse.model_validate_json(resp.text)
        cleaned_bible = sanitize_image_prompt(parsed.character_bible)
        cleaned_scenes = []
        for idx, sc in enumerate(parsed.scenes, start=1):
            cleaned_scenes.append(
                {
                    "scene_index": idx,
                    "narration": sc.narration.strip(),
                    "image_prompt": sanitize_image_prompt(sc.image_prompt),
                }
            )
        if not cleaned_scenes:
            raise ValueError("No scenes were returned by Gemini.")
        return {"character_bible": cleaned_bible, "scenes": cleaned_scenes}

    return _call_text_models_with_fallback(_call, "Scene breakdown generation")


def regenerate_single_scene(
    language: str,
    character_bible: str,
    current_narration: str,
    current_image_prompt: str,
    prev_narration: str = "",
    next_narration: str = "",
) -> Dict[str, str]:
    client = get_gemini_client()
    lang_name = "Hindi (Devanagari script)" if language == "hindi" else "English"

    prompt = f"""
Refine and regenerate ONE storyboard scene so it reads smoothly and has a rich, specific visual prompt.

Language of narration: {lang_name}
Character Bible (must stay consistent): {character_bible}
Previous Scene Narration (context): {prev_narration or "(start of story)"}
Current Scene Narration (to refresh/improve while keeping story continuity): {current_narration}
Current Image Prompt: {current_image_prompt}
Next Scene Narration (context): {next_narration or "(end of story)"}

Return JSON with `scene_index` (use 1), `narration` (in {lang_name}, ~15-25 words), and `image_prompt` (in English, vivid, consistent with Character Bible, zero copyrighted names).
"""

    def _call(model_name: str):
        resp = get_gemini_client().models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SceneItem,
                temperature=0.75,
            ),
        )
        parsed = SceneItem.model_validate_json(resp.text)
        return {
            "narration": parsed.narration.strip(),
            "image_prompt": sanitize_image_prompt(parsed.image_prompt),
        }

    return _call_text_models_with_fallback(_call, "Single scene regeneration")


def rewrite_prompt_for_sd15(scene_prompt: str, character_bible: str) -> str:
    """
    SD 1.5 + LCM-LoRA handles short prompts best. Uses Gemini to condense a scene
    prompt + character visual cues into under 60 words (subject, action, setting, lighting),
    falling back to deterministic trimming if Gemini is unavailable.
    """
    safe_scene = sanitize_image_prompt(scene_prompt)
    safe_bible = sanitize_image_prompt(character_bible)

    # Fast path if already short and no long character bible needs blending
    combined_words = f"{safe_scene} {safe_bible}".split()
    if len(combined_words) <= 35:
        return sanitize_image_prompt(" ".join(combined_words))

    prompt = f"""
Rewrite this scene description for Stable Diffusion 1.5 into ONE compact, vivid English image prompt STRICTLY under 35 words.
Describe ONLY the 2D anime character(s) (hair, outfit colors, expression from Character Bible), action, setting, and lighting.
Do NOT include style words (like watercolor/anime), camera jargon, or ANY copyrighted names.

Character Bible: {safe_bible}
Scene: {safe_scene}

Output ONLY the rewritten prompt text (under 35 words).
"""
    try:
        client = get_gemini_client()

        def _call(model_name: str) -> str:
            resp = get_gemini_client().models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=160,
                ),
            )
            txt = sanitize_image_prompt((resp.text or "").strip().strip('"'))
            words = txt.split()
            if len(words) > 35:
                txt = " ".join(words[:35])
            if not txt:
                raise ValueError("Empty rewrite")
            return txt

        return _call_text_models_with_fallback(_call, "SD 1.5 prompt rewrite")
    except Exception as exc:
        logger.warning("Gemini SD1.5 prompt rewrite failed (%s); using compact fallback.", exc)
        # Deterministic fallback under 35 words
        bible_short = " ".join(safe_bible.split()[:14])
        scene_short = " ".join(safe_scene.split()[:21])
        merged = f"{scene_short}. {bible_short}".strip()
        return " ".join(merged.split()[:35])


def generate_placeholder_watercolor_image(scene_index: int, output_path: Path) -> Path:
    """Create a soft pastel 16:9 anime-watercolor-inspired backdrop for Free-Tier testing."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 1280, 720
    palettes = [
        ((255, 224, 194), (176, 218, 240), (96, 152, 108)),
        ((246, 211, 229), (168, 206, 238), (82, 140, 118)),
        ((254, 238, 198), (195, 224, 210), (108, 158, 96)),
        ((214, 228, 248), (247, 219, 198), (88, 134, 112)),
    ]
    top_col, mid_col, hill_col = palettes[(scene_index - 1) % len(palettes)]

    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top_col[0] * (1 - t) + mid_col[0] * t)
        g = int(top_col[1] * (1 - t) + mid_col[1] * t)
        b = int(top_col[2] * (1 - t) + mid_col[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Dreamy sun glow and soft layered rolling hills
    sun_x = 260 + ((scene_index * 197) % 760)
    sun_y = 170 + ((scene_index * 53) % 90)
    draw.ellipse([(sun_x - 85, sun_y - 85), (sun_x + 85, sun_y + 85)], fill=(255, 248, 220))
    draw.ellipse([(0, 440), (920, 920)], fill=(hill_col[0] + 24, hill_col[1] + 20, hill_col[2] + 18))
    draw.ellipse([(420, 470), (1460, 960)], fill=hill_col)
    img.save(output_path, format="PNG")
    return output_path


def generate_image(full_prompt: str, output_path: Path) -> Path:
    client = get_gemini_client()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_prompt = sanitize_image_prompt(full_prompt)

    def _call(model_name: str) -> Path:
        resp = get_gemini_client().models.generate_content(
            model=model_name,
            contents=safe_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="16:9"),
            ),
        )
        if not resp.candidates or not resp.candidates[0].content or not resp.candidates[0].content.parts:
            raise ValueError("Gemini image response contained no parts.")

        for part in resp.candidates[0].content.parts:
            if getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
                raw_bytes = part.inline_data.data
                img = Image.open(BytesIO(raw_bytes)).convert("RGB")
                img.save(output_path, format="PNG")
                return output_path

        raise ValueError("Gemini image response did not contain inline image data.")

    last_err: Optional[GeminiServiceError] = None
    for model_name in GEMINI_IMAGE_FALLBACK_MODELS:
        try:
            result = with_gemini_retry(
                lambda m=model_name: _call(m),
                f"Image generation ({model_name}, {output_path.name})",
            )
            if GEMINI_REQUEST_DELAY_SEC > 0:
                time.sleep(GEMINI_REQUEST_DELAY_SEC)
            return result
        except GeminiServiceError as exc:
            last_err = exc
            if exc.status_code == 401:
                raise
            logger.warning("Image model %s failed: %s. Trying fallback...", model_name, exc.message)

    assert last_err is not None
    if "limit: 0" in last_err.message.lower():
        raise GeminiServiceError(
            "Gemini Image models returned Free Tier quota = 0 on this API key. "
            "Enable billing in Google AI Studio for AI artwork, or click 'Generate Pastel Test Art' to test video rendering without image quota.",
            status_code=429,
        )
    raise last_err


def generate_youtube_package(
    language: str,
    genre: str,
    topic: str,
    script: str,
    chapter_timestamps: List[Dict[str, str]],
) -> Dict[str, Any]:
    client = get_gemini_client()
    lang_name = "Hindi (Devanagari script)" if language == "hindi" else "English"
    timestamps_text = "\n".join(f"{c['time']} - {c['label']}" for c in chapter_timestamps)

    prompt = f"""
You are a YouTube growth & SEO expert for storytelling channels.
Create a complete YouTube publishing package in {lang_name}.

Story Topic: {topic}
Genre: {GENRE_LABELS.get(genre, genre)}

Accurate Chapter Timestamps from the rendered video (YOU MUST include these timestamps formatted cleanly in the `description`):
{timestamps_text}

Story Script Excerpt:
\"\"\"
{script[:3500]}
\"\"\"

Requirements:
1. `titles`: Exactly 5 high-CTR, curiosity-driven YouTube titles in {lang_name}. EVERY title MUST be strictly under 70 characters (<= 68 chars preferred).
2. `description`: An engaging SEO-optimized YouTube description in {lang_name} that hooks the viewer, summarizes the story without spoiling the ending, includes the exact chapter timestamps above, and ends with a call to subscribe.
3. `tags`: Exactly 15 relevant SEO tags (mix of broad and long-tail keywords, in {lang_name} / Hinglish where helpful).
4. `hashtags`: 6 relevant hashtags starting with `#` (no spaces inside hashtags).
5. `thumbnail_concepts`: Exactly 3 distinct, high-CTR thumbnail concepts:
   - `concept_title`: Short name of the concept
   - `visual_description`: Detailed English visual prompt for a dramatic 16:9 hand-painted anime watercolor background (no copyrighted names, leave space for bold text)
   - `overlay_text`: Short, punchy 2-5 word bold thumbnail text in {lang_name}
   - `accent_color`: Hex color like "#FFD166" or "#FF6B6B" or "#4ECDC4"
"""

    def _call(model_name: str):
        resp = get_gemini_client().models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=YouTubePackageModel,
                temperature=0.8,
            ),
        )
        parsed = YouTubePackageModel.model_validate_json(resp.text)
        data = parsed.model_dump()
        # Enforce strict <= 70 char limit on titles
        enforced_titles = []
        for t in data["titles"][:5]:
            t = t.strip()
            if len(t) > 70:
                t = t[:67].rstrip() + "..."
            enforced_titles.append(t)
        data["titles"] = enforced_titles
        data["tags"] = [tag.strip() for tag in data["tags"][:15]]
        data["hashtags"] = [
            h if h.startswith("#") else f"#{h.replace(' ', '')}" for h in data["hashtags"]
        ]
        data["thumbnail_concepts"] = data["thumbnail_concepts"][:3]
        return data

    return _call_text_models_with_fallback(_call, "YouTube package generation")
