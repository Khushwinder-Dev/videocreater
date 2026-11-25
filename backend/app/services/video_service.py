import logging
import subprocess
import tempfile
import textwrap
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from moviepy import AudioFileClip, concatenate_audioclips

from .font_service import ensure_devanagari_font, ensure_latin_font
from .tts_service import get_audio_duration

logger = logging.getLogger(__name__)

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_FPS = 24
SCENE_PAUSE_SEC = 0.35
CROSSFADE_SEC = 0.40
_CANCEL_TLS = threading.local()


class RenderCancelledError(Exception):
    """Raised when a video render task is stopped by the user."""


def _check_render_cancelled() -> None:
    cb = getattr(_CANCEL_TLS, "cancel_cb", None)
    if cb and cb():
        raise RenderCancelledError("Video render stopped by user.")


def _run_ffmpeg(cmd: List[str], step_label: str) -> None:
    _check_render_cancelled()
    cancel_cb = getattr(_CANCEL_TLS, "cancel_cb", None)
    if not cancel_cb:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            err_tail = (res.stderr or res.stdout or "")[-800:]
            raise RuntimeError(f"FFmpeg failed during {step_label}: {err_tail}")
        return

    with tempfile.TemporaryFile(mode="w+b") as stderr_file:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
        )
        while proc.poll() is None:
            if cancel_cb():
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2.0)
                raise RenderCancelledError(f"Video render stopped during {step_label}.")
            time.sleep(0.35)

        if proc.returncode != 0:
            stderr_file.seek(0)
            err_tail = stderr_file.read().decode("utf-8", "ignore")[-800:]
            raise RuntimeError(f"FFmpeg failed during {step_label}: {err_tail}")


def _escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape Windows/Posix paths for FFmpeg filter arguments (ass/subtitles)."""
    p = str(path.resolve()).replace("\\", "/")
    # Escape drive colon e.g. D:/... -> D\:/...
    p = p.replace(":", "\\:")
    p = p.replace("'", "\\'")
    return p


def _format_ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"


def format_yt_timestamp(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def calculate_scene_timeline(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute exact start/end times for each scene including breathing pause."""
    timeline = []
    cursor = 0.0
    for sc in scenes:
        audio_path = Path(sc["audio_path"])
        dur = float(sc.get("audio_duration_sec") or 0.0)
        if dur <= 0.05 and audio_path.exists():
            dur = get_audio_duration(audio_path)
        dur = max(1.0, dur)
        slot_dur = dur + SCENE_PAUSE_SEC
        timeline.append(
            {
                "scene_index": sc["scene_index"],
                "narration": sc["narration"],
                "image_path": sc["image_path"],
                "audio_path": str(audio_path),
                "voice_duration": dur,
                "slot_duration": slot_dur,
                "start_sec": cursor,
                "voice_end_sec": cursor + dur,
                "end_sec": cursor + slot_dur,
            }
        )
        cursor += slot_dur
    return timeline


def _split_caption_chunks(text: str, voice_dur: float, start_sec: float, language: str) -> List[Dict[str, Any]]:
    """Split a scene narration into 1-2 short readable subtitle chunks timed proportionally."""
    words = text.strip().split()
    if not words:
        return []

    max_chars_per_line = 38 if language == "hindi" else 44
    max_words_per_chunk = 11 if language == "hindi" else 13

    if len(words) <= max_words_per_chunk:
        wrapped = "\\N".join(textwrap.wrap(" ".join(words), width=max_chars_per_line))
        return [{"start": start_sec, "end": start_sec + voice_dur, "text": wrapped}]

    # Split into balanced chunks
    mid = len(words) // 2
    chunks_words = [words[:mid], words[mid:]]
    total_chars = max(1, sum(len(" ".join(cw)) for cw in chunks_words))
    cursor = start_sec
    events = []
    for cw in chunks_words:
        chunk_str = " ".join(cw)
        ratio = len(chunk_str) / total_chars
        chunk_dur = max(0.8, voice_dur * ratio)
        wrapped = "\\N".join(textwrap.wrap(chunk_str, width=max_chars_per_line))
        events.append({"start": cursor, "end": min(start_sec + voice_dur, cursor + chunk_dur), "text": wrapped})
        cursor += chunk_dur
    if events:
        events[-1]["end"] = start_sec + voice_dur
    return events


def write_ass_subtitles(
    timeline: List[Dict[str, Any]],
    language: str,
    ass_path: Path,
) -> tuple[Path, Optional[Path]]:
    if language == "hindi":
        font_family, font_file = ensure_devanagari_font()
        font_size = 54
    else:
        font_family, font_file = ensure_latin_font()
        font_size = 50

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {TARGET_WIDTH}
PlayResY: {TARGET_HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_family},{font_size},&H00FFFFFF,&H000000FF,&H00101218,&H96000000,-1,0,0,0,100,100,0,0,1,3.2,1.5,2,90,90,62,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for item in timeline:
        events = _split_caption_chunks(
            item["narration"],
            item["voice_duration"],
            item["start_sec"],
            language,
        )
        for ev in events:
            safe_text = ev["text"].replace("{", "(").replace("}", ")")
            lines.append(
                f"Dialogue: 0,{_format_ass_time(ev['start'])},{_format_ass_time(ev['end'])},Default,,0,0,0,,{safe_text}\n"
            )

    ass_path.write_text("".join(lines), encoding="utf-8")
    fonts_dir = font_file.parent if font_file else None
    return ass_path, fonts_dir


def _render_ken_burns_clip(
    image_path: Path,
    duration_sec: float,
    preset_index: int,
    output_clip: Path,
) -> None:
    """
    Render a single 1920x1080@24fps Ken Burns clip from a still image using FFmpeg.
    Upscaling before zoompan eliminates subpixel jitter.
    """
    total_frames = max(24, int(round(duration_sec * TARGET_FPS)))
    denom = max(1, total_frames - 1)
    mode = preset_index % 4

    if mode == 0:
        # Gentle zoom in toward center
        z_expr = f"1.0+0.10*(on/{denom})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif mode == 1:
        # Gentle zoom out from center
        z_expr = f"1.10-0.10*(on/{denom})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif mode == 2:
        # Slow pan left -> right at slight zoom
        z_expr = "1.08"
        x_expr = f"(iw-iw/zoom)*(on/{denom})"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        # Slow pan right -> left at slight zoom
        z_expr = "1.08"
        x_expr = f"(iw-iw/zoom)*(1.0-(on/{denom}))"
        y_expr = "ih/2-(ih/zoom/2)"

    vf = (
        f"scale=3840:2160:force_original_aspect_ratio=increase,"
        f"crop=3840:2160,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={TARGET_WIDTH}x{TARGET_HEIGHT}:fps={TARGET_FPS},"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(image_path),
        "-vf",
        vf,
        "-t",
        f"{duration_sec:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-r",
        str(TARGET_FPS),
        "-an",
        str(output_clip),
    ]
    _run_ffmpeg(cmd, f"Ken Burns clip {output_clip.name}")


def _xfade_batch(clips: List[Path], slot_durations: List[float], fade_dur: float, output_path: Path) -> float:
    """Join a small batch of clips with FFmpeg xfade transitions. Returns total resulting duration."""
    if len(clips) == 1:
        # Copy single clip directly
        cmd = ["ffmpeg", "-y", "-i", str(clips[0]), "-c", "copy", str(output_path)]
        _run_ffmpeg(cmd, f"Copy single clip {output_path.name}")
        return slot_durations[0]

    cmd = ["ffmpeg", "-y"]
    for c in clips:
        cmd.extend(["-i", str(c)])

    filter_parts = []
    cumulative = slot_durations[0]
    prev_label = "[0:v]"
    for idx in range(1, len(clips)):
        out_label = f"[v{idx}]" if idx < len(clips) - 1 else "[vout]"
        offset = max(0.05, cumulative - fade_dur)
        filter_parts.append(
            f"{prev_label}[{idx}:v]xfade=transition=fade:duration={fade_dur:.3f}:offset={offset:.3f}{out_label}"
        )
        prev_label = out_label
        cumulative = offset + slot_durations[idx]

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[vout]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-r",
            str(TARGET_FPS),
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
    )
    _run_ffmpeg(cmd, f"xfade batch {output_path.name}")
    return cumulative


def _build_master_narration_audio(
    timeline: List[Dict[str, Any]],
    render_dir: Path,
) -> Path:
    """
    Use MoviePy AudioFileClip + FFmpeg padding to build an exact-timing master narration WAV
    matching the timeline slot durations.
    """
    padded_wavs: List[Path] = []
    concat_list_path = render_dir / "audio_concat.txt"

    for item in timeline:
        idx = item["scene_index"]
        src_wav = Path(item["audio_path"])
        padded_wav = render_dir / f"padded_audio_{idx:03d}.wav"

        # Probe with MoviePy to verify audio readability
        with AudioFileClip(str(src_wav)) as clip:
            actual_dur = float(clip.duration or item["voice_duration"])

        pad_needed = max(0.0, item["slot_duration"] - actual_dur)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(src_wav),
            "-af",
            f"apad=pad_dur={pad_needed:.3f},atrim=0:{item['slot_duration']:.3f}",
            "-ac",
            "2",
            "-ar",
            "44100",
            str(padded_wav),
        ]
        _run_ffmpeg(cmd, f"Pad narration scene {idx}")
        padded_wavs.append(padded_wav)

    # Concatenate via MoviePy for clean sample-accurate join, falling back to ffmpeg concat
    master_wav = render_dir / "master_narration.wav"
    clips = [AudioFileClip(str(p)) for p in padded_wavs]
    try:
        combined = concatenate_audioclips(clips)
        combined.write_audiofile(str(master_wav), fps=44100, logger=None)
        combined.close()
    finally:
        for c in clips:
            c.close()

    concat_list_path.unlink(missing_ok=True)
    return master_wav


def render_project_video(
    project: Dict[str, Any],
    scenes: List[Dict[str, Any]],
    render_dir: Path,
    bgm_path: Optional[Path],
    bgm_volume: float,
    auto_duck: bool,
    burn_subtitles: bool,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    max_duration_sec: Optional[float] = None,
    output_filename: str = "final_video.mp4",
    cancel_cb: Optional[Callable[[], bool]] = None,
) -> Path:
    _CANCEL_TLS.cancel_cb = cancel_cb
    try:
        return _render_project_video_impl(
            project=project,
            scenes=scenes,
            render_dir=render_dir,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            auto_duck=auto_duck,
            burn_subtitles=burn_subtitles,
            progress_cb=progress_cb,
            max_duration_sec=max_duration_sec,
            output_filename=output_filename,
        )
    finally:
        _CANCEL_TLS.cancel_cb = None


def _render_project_video_impl(
    project: Dict[str, Any],
    scenes: List[Dict[str, Any]],
    render_dir: Path,
    bgm_path: Optional[Path],
    bgm_volume: float,
    auto_duck: bool,
    burn_subtitles: bool,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    max_duration_sec: Optional[float] = None,
    output_filename: str = "final_video.mp4",
) -> Path:
    def report(pct: int, msg: str) -> None:
        if progress_cb:
            progress_cb(pct, msg)

    render_dir.mkdir(parents=True, exist_ok=True)
    valid_scenes = [
        s
        for s in scenes
        if s.get("audio_path")
        and Path(s["audio_path"]).exists()
        and s.get("image_path")
        and Path(s["image_path"]).exists()
    ]
    if len(valid_scenes) != len(scenes) or not valid_scenes:
        raise ValueError(
            "Every scene must have both a generated voiceover and a generated image before rendering."
        )

    report(3, "Calculating exact scene timeline...")
    timeline = calculate_scene_timeline(valid_scenes)
    if max_duration_sec and max_duration_sec > 0:
        trimmed = []
        acc = 0.0
        for item in timeline:
            trimmed.append(item)
            acc += item["slot_duration"]
            if acc >= max_duration_sec and len(trimmed) >= 1:
                break
        timeline = trimmed
    total_scenes = len(timeline)

    # 1. Render per-scene Ken Burns clips (with extra tail overlap for crossfade on non-last scenes)
    scene_clips: List[Path] = []
    clip_durations: List[float] = []
    for i, item in enumerate(timeline):
        is_last = i == total_scenes - 1
        clip_dur = item["slot_duration"] + (0.0 if is_last else CROSSFADE_SEC)
        clip_path = render_dir / f"scene_clip_{item['scene_index']:03d}.mp4"
        report(
            5 + int((i / total_scenes) * 50),
            f"Rendering Ken Burns animation for scene {i + 1}/{total_scenes}...",
        )
        _render_ken_burns_clip(Path(item["image_path"]), clip_dur, i, clip_path)
        scene_clips.append(clip_path)
        clip_durations.append(clip_dur)

    # 2. Crossfade clips in manageable batches of 10, then crossfade batch outputs
    report(58, "Applying smooth crossfade transitions between scenes...")
    batch_size = 10
    batch_outputs: List[Path] = []
    batch_durations: List[float] = []

    if len(scene_clips) <= batch_size:
        joined_video = render_dir / "video_joined.mp4"
        _xfade_batch(scene_clips, clip_durations, CROSSFADE_SEC, joined_video)
    else:
        for b_idx in range(0, len(scene_clips), batch_size):
            chunk_clips = scene_clips[b_idx : b_idx + batch_size]
            chunk_durs = clip_durations[b_idx : b_idx + batch_size]
            out_batch = render_dir / f"batch_{b_idx // batch_size:02d}.mp4"
            res_dur = _xfade_batch(chunk_clips, chunk_durs, CROSSFADE_SEC, out_batch)
            batch_outputs.append(out_batch)
            batch_durations.append(res_dur)

        report(68, "Merging video batches with seamless transitions...")
        joined_video = render_dir / "video_joined.mp4"
        _xfade_batch(batch_outputs, batch_durations, CROSSFADE_SEC, joined_video)

    # 3. Build exact-sync master narration track
    report(74, "Synchronizing per-scene voiceover tracks...")
    master_voice = _build_master_narration_audio(timeline, render_dir)
    total_video_dur = sum(t["slot_duration"] for t in timeline)

    # 4. Mix optional background music with auto-ducking
    final_audio = master_voice
    if bgm_path and bgm_path.exists():
        report(82, "Mixing background music with automatic voice ducking...")
        mixed_audio = render_dir / "master_mixed.wav"
        vol = max(0.02, min(1.0, bgm_volume))
        if auto_duck:
            # Sidechain ducking compresses BGM whenever narrator voice is active
            af_complex = (
                f"[1:a]volume={vol:.3f}[bgm];"
                f"[0:a]asplit=2[voice_main][voice_sc];"
                f"[bgm][voice_sc]sidechaincompress=threshold=0.02:ratio=6:attack=40:release=350[bgm_ducked];"
                f"[voice_main][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2,"
                f"alimiter=limit=0.95[aout]"
            )
        else:
            af_complex = (
                f"[1:a]volume={vol:.3f}[bgm];"
                f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2,"
                f"alimiter=limit=0.95[aout]"
            )

        cmd_mix = [
            "ffmpeg",
            "-y",
            "-i",
            str(master_voice),
            "-stream_loop",
            "-1",
            "-i",
            str(bgm_path),
            "-filter_complex",
            af_complex,
            "-map",
            "[aout]",
            "-t",
            f"{total_video_dur:.3f}",
            "-ac",
            "2",
            "-ar",
            "44100",
            str(mixed_audio),
        ]
        _run_ffmpeg(cmd_mix, "BGM auto-duck audio mix")
        final_audio = mixed_audio

    # 5. Burn subtitles (if enabled) + mux final 1920x1080 24fps MP4
    final_output = render_dir / output_filename
    report(90, "Burning subtitles and encoding 1080p 24fps MP4...")

    cmd_final = [
        "ffmpeg",
        "-y",
        "-i",
        str(joined_video),
        "-i",
        str(final_audio),
    ]

    if burn_subtitles:
        ass_path, fonts_dir = write_ass_subtitles(
            timeline,
            project.get("language", "english"),
            render_dir / "subtitles.ass",
        )
        esc_ass = _escape_ffmpeg_filter_path(ass_path)
        if fonts_dir:
            esc_fonts = _escape_ffmpeg_filter_path(fonts_dir)
            vf_sub = f"ass='{esc_ass}':fontsdir='{esc_fonts}'"
        else:
            vf_sub = f"ass='{esc_ass}'"
        cmd_final.extend(["-vf", vf_sub])
        cmd_final.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p"])
    else:
        cmd_final.extend(["-c:v", "copy"])

    cmd_final.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-r",
            str(TARGET_FPS),
            "-shortest",
            "-movflags",
            "+faststart",
            str(final_output),
        ]
    )
    _run_ffmpeg(cmd_final, "Final MP4 encode")

    # Clean up intermediate video clips to conserve disk space
    for tmp in scene_clips + batch_outputs:
        tmp.unlink(missing_ok=True)

    report(100, "Video render complete!")
    return final_output
