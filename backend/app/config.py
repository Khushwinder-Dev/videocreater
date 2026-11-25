import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve repository root: .../backend/app/config.py -> parents[2]
ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
FONTS_DIR = BACKEND_DIR / "fonts"

# Load root .env if present
load_dotenv(ROOT_DIR / ".env")


def _resolve_path(raw: str, default_rel: str) -> Path:
    p = Path(raw or default_rel)
    if not p.is_absolute():
        p = (ROOT_DIR / p).resolve()
    return p


def _parse_api_keys() -> list[str]:
    raw = ",".join(
        part for part in (os.getenv("GEMINI_API_KEYS", ""), os.getenv("GEMINI_API_KEY", "")) if part
    )
    keys = [
        k.strip()
        for k in raw.replace("\n", ",").split(",")
        if k.strip() and k.strip() != "your_gemini_api_key_here"
    ]
    return list(dict.fromkeys(keys))


GEMINI_API_KEYS: list[str] = _parse_api_keys()
GEMINI_API_KEY: str = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
GEMINI_TEXT_MODEL: str = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash").strip()
GEMINI_TEXT_FALLBACK_MODELS: list[str] = list(
    dict.fromkeys(
        [
            GEMINI_TEXT_MODEL,
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.1-flash-lite",
        ]
    )
)
GEMINI_IMAGE_MODEL: str = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image").strip()
GEMINI_IMAGE_FALLBACK_MODELS: list[str] = list(
    dict.fromkeys([GEMINI_IMAGE_MODEL, "gemini-3.1-flash-image", "gemini-3.1-flash-lite-image", "gemini-2.5-flash-image"])
)
GEMINI_TTS_MODEL: str = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts").strip()
GEMINI_TTS_FALLBACK_MODEL: str = os.getenv(
    "GEMINI_TTS_FALLBACK_MODEL", "gemini-2.5-flash-preview-tts"
).strip()

# Local SD (FastSD CPU + Real-ESRGAN / Upscayl) Configuration
DEFAULT_PROVIDER: str = os.getenv("DEFAULT_PROVIDER", "local_sd").strip().lower()
if DEFAULT_PROVIDER not in ("local_sd", "gemini"):
    DEFAULT_PROVIDER = "local_sd"
FASTSD_URL: str = os.getenv("FASTSD_URL", "http://127.0.0.1:8000").strip().rstrip("/")
FASTSD_DIR: Path = ROOT_DIR / "tools" / "fastsdcpu"
_DEFAULT_UPSCALER = (
    "./tools/upscayl/realesrgan-ncnn-vulkan.exe"
    if os.name == "nt"
    else "./tools/upscayl/realesrgan-ncnn-vulkan"
)
UPSCAYL_BIN: str = os.getenv("UPSCAYL_BIN", _DEFAULT_UPSCALER).strip()
FASTSD_STEPS: int = max(4, min(6, int(os.getenv("FASTSD_STEPS", "6"))))
FASTSD_GUIDANCE: float = max(1.0, min(1.5, float(os.getenv("FASTSD_GUIDANCE", "1.4"))))
UPSCALE_ENABLED: bool = os.getenv("UPSCALE_ENABLED", "true").strip().lower() in ("1", "true", "yes")

BACKEND_HOST: str = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8001"))

PROJECTS_DIR: Path = _resolve_path(os.getenv("PROJECTS_DIR", "./projects"), "./projects")
DB_PATH: Path = _resolve_path(
    os.getenv("DB_PATH", str(PROJECTS_DIR / "storytube.db")),
    "./projects/storytube.db",
)

GEMINI_MAX_RETRIES: int = int(os.getenv("GEMINI_MAX_RETRIES", "5"))
GEMINI_REQUEST_DELAY_SEC: float = float(os.getenv("GEMINI_REQUEST_DELAY_SEC", "1.2"))

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)

# Fixed style prefix and negative prompt for Local SD 1.5 + LCM-LoRA
LOCAL_STYLE_PREFIX = (
    "hand-painted anime watercolor, soft pastel colors, lush green nature, "
    "dreamy sky, warm golden light, detailed painterly background, "
    "gentle whimsical mood, studio-quality illustration"
)
LOCAL_NEGATIVE_PROMPT = (
    "photorealistic, real person, realistic, photo, 3d render, CGI, semi-realistic, "
    "skin pores, live action, text, watermark, logo, blurry, "
    "deformed face, distorted face, ugly face, smudged face, asymmetrical eyes, "
    "bad eyes, bad anatomy, deformed hands, extra limbs, low quality"
)

# Fixed visual style directive for Gemini Image fallback
ANIME_WATERCOLOR_STYLE = (
    "hand-painted anime watercolor illustration style, soft pastel colors, "
    "lush green nature, dreamy skies, warm golden lighting, detailed painterly backgrounds, "
    "gentle whimsical mood, cinematic 16:9 widescreen framing, clean composition, "
    "no text, no subtitles, no watermarks, no borders"
)

# Copyrighted studio/franchise terms stripped from image prompts automatically
COPYRIGHTED_TERMS = [
    "studio ghibli",
    "ghibli",
    "miyazaki",
    "hayao miyazaki",
    "makoto shinkai",
    "disney",
    "pixar",
    "dreamworks",
    "marvel",
    "dc comics",
    "pokemon",
    "pikachu",
    "naruto",
    "one piece",
    "dragon ball",
    "demon slayer",
    "attack on titan",
    "harry potter",
    "totoro",
    "spirited away",
    "frozen",
    "elsa",
    "mickey mouse",
    "spiderman",
    "spider-man",
    "batman",
    "superman",
    "doraemon",
    "shinchan",
    "chhota bheem",
    "motu patlu",
]

# Curated selectable voices for Gemini TTS + matching edge-tts fallbacks
VOICE_OPTIONS = {
    "hindi": [
        {
            "id": "Kore",
            "label": "Kore — Warm Storytelling (Female)",
            "gemini_voice": "Kore",
            "edge_voice": "hi-IN-SwaraNeural",
            "style_hint": "Speak in warm, expressive Hindi storytelling cadence with gentle emotion.",
        },
        {
            "id": "Aoede",
            "label": "Aoede — Soft Melodic (Female)",
            "gemini_voice": "Aoede",
            "edge_voice": "hi-IN-SwaraNeural",
            "style_hint": "Speak in soft, soothing, heartwarming Hindi narration.",
        },
        {
            "id": "Zephyr",
            "label": "Zephyr — Bright & Clear (Neutral)",
            "gemini_voice": "Zephyr",
            "edge_voice": "hi-IN-SwaraNeural",
            "style_hint": "Speak in clear, engaging, gentle Hindi narration suitable for all ages.",
        },
        {
            "id": "Charon",
            "label": "Charon — Deep & Wise (Male)",
            "gemini_voice": "Charon",
            "edge_voice": "hi-IN-MadhurNeural",
            "style_hint": "Speak in a calm, deep, wise Hindi storyteller voice.",
        },
        {
            "id": "Puck",
            "label": "Puck — Playful & Lively (Male)",
            "gemini_voice": "Puck",
            "edge_voice": "hi-IN-MadhurNeural",
            "style_hint": "Speak in an animated, friendly, lively Hindi storytelling tone.",
        },
    ],
    "english": [
        {
            "id": "Aoede",
            "label": "Aoede — Warm & Emotive (Female)",
            "gemini_voice": "Aoede",
            "edge_voice": "en-US-AvaNeural",
            "style_hint": "Speak in warm, gentle, emotive English storytelling narration.",
        },
        {
            "id": "Kore",
            "label": "Kore — Calm & Crisp (Female)",
            "gemini_voice": "Kore",
            "edge_voice": "en-GB-SoniaNeural",
            "style_hint": "Speak in a soothing, clear, heartfelt English narrative voice.",
        },
        {
            "id": "Zephyr",
            "label": "Zephyr — Bright & Whimsical (Neutral)",
            "gemini_voice": "Zephyr",
            "edge_voice": "en-US-EmmaNeural",
            "style_hint": "Speak in a bright, gentle, whimsical English story voice.",
        },
        {
            "id": "Charon",
            "label": "Charon — Deep & Cinematic (Male)",
            "gemini_voice": "Charon",
            "edge_voice": "en-US-AndrewNeural",
            "style_hint": "Speak in a deep, thoughtful, cinematic English storyteller voice.",
        },
        {
            "id": "Fenrir",
            "label": "Fenrir — Dramatic & Rich (Male)",
            "gemini_voice": "Fenrir",
            "edge_voice": "en-US-BrianNeural",
            "style_hint": "Speak in a rich, atmospheric English narrative voice.",
        },
    ],
}

GENRE_LABELS = {
    "moral_stories": "Moral Stories",
    "kids": "Kids & Bedtime",
    "mythology": "Mythology & Folklore",
    "mystery": "Mystery & Suspense",
    "horror": "Horror Stories",
}
