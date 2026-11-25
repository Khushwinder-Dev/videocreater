import asyncio
import logging
import re
import subprocess
import time
import wave
from pathlib import Path
from typing import Dict, Optional, Tuple

import edge_tts
from google.genai import types

from ..config import (
    GEMINI_API_KEY,
    GEMINI_REQUEST_DELAY_SEC,
    GEMINI_TTS_FALLBACK_MODEL,
    GEMINI_TTS_MODEL,
    VOICE_OPTIONS,
)
from .gemini_service import get_gemini_client, with_gemini_retry

logger = logging.getLogger(__name__)


def get_voice_meta(language: str, voice_id: str) -> Dict[str, str]:
    options = VOICE_OPTIONS.get(language, VOICE_OPTIONS["english"])
    for opt in options:
        if opt["id"] == voice_id:
            return opt
    return options[0]


def get_audio_duration(audio_path: Path) -> float:
    """Measure exact audio duration in seconds using wave or ffprobe."""
    if audio_path.suffix.lower() == ".wav":
        try:
            with wave.open(str(audio_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return round(frames / float(rate), 3)
        except Exception:
            pass

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode == 0 and res.stdout.strip():
        try:
            return round(float(res.stdout.strip()), 3)
        except ValueError:
            pass
    return 0.0


def _write_audio_bytes_as_wav(audio_bytes: bytes, mime_type: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # If Gemini already returned a WAV container (RIFF header), write directly then normalize
    if audio_bytes[:4] == b"RIFF":
        tmp_raw = output_path.with_suffix(".raw.wav")
        tmp_raw.write_bytes(audio_bytes)
        _normalize_to_wav(tmp_raw, output_path)
        tmp_raw.unlink(missing_ok=True)
        return

    # Otherwise wrap raw L16 PCM bytes in a WAV header
    sample_rate = 24000
    rate_match = re.search(r"rate=(\d+)", mime_type or "")
    if rate_match:
        sample_rate = int(rate_match.group(1))

    tmp_pcm = output_path.with_suffix(".pcm.wav")
    with wave.open(str(tmp_pcm), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_bytes)

    _normalize_to_wav(tmp_pcm, output_path)
    tmp_pcm.unlink(missing_ok=True)


def _normalize_to_wav(src_path: Path, dst_path: Path) -> None:
    """Convert any audio input to uniform 24kHz mono 16-bit WAV via FFmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src_path),
        "-ac",
        "1",
        "-ar",
        "24000",
        "-sample_fmt",
        "s16",
        str(dst_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg audio normalization failed: {res.stderr[-400:]}")


def _gemini_tts_once(
    text: str,
    model_name: str,
    voice_name: str,
    style_hint: str,
    output_path: Path,
) -> Path:
    client = get_gemini_client(api_version="v1beta")
    prompt = f"{style_hint}\n\nRead the following narration clearly and naturally:\n{text}"

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )

    if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
        raise ValueError(f"{model_name} returned no audio parts.")

    for part in response.candidates[0].content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            _write_audio_bytes_as_wav(inline.data, getattr(inline, "mime_type", "") or "", output_path)
            return output_path

    raise ValueError(f"{model_name} did not include inline audio data.")


async def _edge_tts_async(text: str, edge_voice: str, mp3_path: Path) -> None:
    communicate = edge_tts.Communicate(text=text, voice=edge_voice, rate="-4%")
    await communicate.save(str(mp3_path))


def _synthesize_with_edge_tts(text: str, edge_voice: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp3 = output_path.with_suffix(".edge.mp3")
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Run in a separate thread when called inside an active event loop
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(lambda: asyncio.run(_edge_tts_async(text, edge_voice, tmp_mp3))).result()
        else:
            asyncio.run(_edge_tts_async(text, edge_voice, tmp_mp3))

        _normalize_to_wav(tmp_mp3, output_path)
        return output_path
    finally:
        tmp_mp3.unlink(missing_ok=True)


def synthesize_speech(
    text: str,
    language: str,
    voice_id: str,
    output_path: Path,
) -> Tuple[Path, float, str]:
    """
    Generate speech audio as WAV.
    Tries primary Gemini TTS model -> fallback Gemini TTS model -> edge-tts fallback.
    Returns (output_path, duration_sec, provider_used).
    """
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Cannot synthesize empty narration text.")

    voice_meta = get_voice_meta(language, voice_id)
    gemini_voice = voice_meta["gemini_voice"]
    edge_voice = voice_meta["edge_voice"]
    style_hint = voice_meta["style_hint"]

    # Attempt Gemini TTS if API key is configured
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        models_to_try = [GEMINI_TTS_MODEL]
        if GEMINI_TTS_FALLBACK_MODEL and GEMINI_TTS_FALLBACK_MODEL != GEMINI_TTS_MODEL:
            models_to_try.append(GEMINI_TTS_FALLBACK_MODEL)

        for model_name in models_to_try:
            try:
                with_gemini_retry(
                    lambda m=model_name: _gemini_tts_once(
                        clean_text, m, gemini_voice, style_hint, output_path
                    ),
                    operation_name=f"Gemini TTS ({model_name})",
                )
                duration = get_audio_duration(output_path)
                if duration > 0.1:
                    if GEMINI_REQUEST_DELAY_SEC > 0:
                        time.sleep(min(0.8, GEMINI_REQUEST_DELAY_SEC))
                    return output_path, duration, f"gemini ({model_name})"
            except Exception as exc:
                logger.warning("Gemini TTS (%s) failed: %s", model_name, exc)

    # Automatic fallback to edge-tts
    logger.info("Falling back to edge-tts (%s) for %s", edge_voice, output_path.name)
    _synthesize_with_edge_tts(clean_text, edge_voice, output_path)
    duration = get_audio_duration(output_path)
    return output_path, duration, f"edge-tts ({edge_voice})"


def synthesize_voice_preview(language: str, voice_id: str, output_path: Path) -> Tuple[Path, float, str]:
    if language == "hindi":
        sample = (
            "नमस्ते, स्टोरीट्यूब स्टूडियो में आपका स्वागत है। "
            "आज हम एक बेहद खूबसूरत और दिल छू लेने वाली कहानी सुनने जा रहे हैं।"
        )
    else:
        sample = (
            "Welcome to StoryTube Studio. "
            "Listen closely, because every quiet village hides a story waiting to be told."
        )
    return synthesize_speech(sample, language, voice_id, output_path)
