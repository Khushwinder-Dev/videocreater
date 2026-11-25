import logging
import random
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import database as db
from .config import (
    ANIME_WATERCOLOR_STYLE,
    GEMINI_API_KEY,
    GEMINI_IMAGE_MODEL,
    GEMINI_TEXT_MODEL,
    GEMINI_TTS_MODEL,
    LOCAL_STYLE_PREFIX,
    PROJECTS_DIR,
    VOICE_OPTIONS,
)
from .models import (
    AppSettingsUpdateRequest,
    ImagesBatchRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    ScenesBulkUpdateRequest,
    SceneUpdateRequest,
    SingleImageRegenRequest,
    ThumbnailRegenerateRequest,
    TopicSelectRequest,
    VideoRenderRequest,
    VoiceBatchRequest,
    VoicePreviewRequest,
)
from .services import (
    gemini_service,
    local_image_service,
    thumbnail_service,
    tts_service,
    video_service,
)
from .services.gemini_service import GeminiServiceError
from .services.local_image_service import LocalImageServiceError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("storytube")

app = FastAPI(title="StoryTube Studio API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

# Static serving for generated project media + voice previews
PREVIEW_DIR = PROJECTS_DIR / "_previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(PROJECTS_DIR)), name="media")

# Thread-safe background job tracker: key = f"{project_id}:{task_type}"
_TASKS_LOCK = threading.Lock()
_TASKS: Dict[str, Dict[str, Any]] = {}
_CANCEL_EVENTS: Dict[str, threading.Event] = {}


class TaskCancelledError(Exception):
    """Raised internally when a user requests stopping an active background task."""


def _reset_cancel(project_id: str, task_type: str) -> threading.Event:
    key = f"{project_id}:{task_type}"
    with _TASKS_LOCK:
        ev = threading.Event()
        _CANCEL_EVENTS[key] = ev
        return ev


def _request_cancel(project_id: str, task_type: str) -> bool:
    key = f"{project_id}:{task_type}"
    with _TASKS_LOCK:
        ev = _CANCEL_EVENTS.get(key)
        if ev is None:
            ev = threading.Event()
            _CANCEL_EVENTS[key] = ev
        ev.set()
        return True


def _is_cancelled(project_id: str, task_type: str) -> bool:
    key = f"{project_id}:{task_type}"
    with _TASKS_LOCK:
        ev = _CANCEL_EVENTS.get(key)
        return bool(ev and ev.is_set())


def _set_task(project_id: str, task_type: str, **updates: Any) -> None:
    key = f"{project_id}:{task_type}"
    with _TASKS_LOCK:
        cur = _TASKS.get(
            key,
            {
                "status": "idle",
                "progress": 0,
                "completed_items": 0,
                "total_items": 0,
                "cancel_requested": False,
                "message": "",
                "error": None,
            },
        )
        cur.update(updates)
        _TASKS[key] = cur


def _get_task(project_id: str, task_type: str) -> Dict[str, Any]:
    key = f"{project_id}:{task_type}"
    with _TASKS_LOCK:
        return dict(
            _TASKS.get(
                key,
                {
                    "status": "idle",
                    "progress": 0,
                    "completed_items": 0,
                    "total_items": 0,
                    "cancel_requested": False,
                    "message": "",
                    "error": None,
                },
            )
        )


def _to_media_url(abs_path: str) -> str:
    if not abs_path:
        return ""
    try:
        rel = Path(abs_path).resolve().relative_to(PROJECTS_DIR.resolve())
        return "/media/" + rel.as_posix()
    except Exception:
        return ""


def _enrich_project(project: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not project:
        return None
    project["bgm_url"] = _to_media_url(project.get("bgm_path", "")) if project.get("bgm_path") and Path(project["bgm_path"]).exists() else ""
    project["video_url"] = _to_media_url(project.get("video_path", "")) if project.get("video_path") and Path(project["video_path"]).exists() else ""
    preview_file = PROJECTS_DIR / project["id"] / "render" / "test_preview_15s.mp4"
    project["preview_video_url"] = _to_media_url(str(preview_file)) if preview_file.exists() else ""

    if "scenes" in project and isinstance(project["scenes"], list):
        for sc in project["scenes"]:
            ap = sc.get("audio_path", "")
            ip = sc.get("image_path", "")
            sc["audio_url"] = _to_media_url(ap) if ap and Path(ap).exists() else ""
            sc["image_url"] = _to_media_url(ip) if ip and Path(ip).exists() else ""

    yt = project.get("youtube_package") or {}
    if isinstance(yt, dict) and isinstance(yt.get("thumbnail_concepts"), list):
        for concept in yt["thumbnail_concepts"]:
            tp = concept.get("image_path", "")
            concept["image_url"] = _to_media_url(tp) if tp and Path(tp).exists() else ""

    return project


@app.exception_handler(GeminiServiceError)
async def gemini_error_handler(_request: Request, exc: GeminiServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(LocalImageServiceError)
async def local_image_error_handler(_request: Request, exc: LocalImageServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/api/health")
def health_check():
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    key_ok = bool(GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here")
    settings = db.get_app_settings()
    local_status = local_image_service.check_services(settings)
    return {
        "status": "ok",
        "gemini_configured": key_ok,
        "ffmpeg_installed": ffmpeg_ok,
        "models": {
            "text": GEMINI_TEXT_MODEL,
            "image": "FastSD CPU (SD 1.5 + LCM-LoRA)" if settings["image_provider"] == "local_sd" else GEMINI_IMAGE_MODEL,
            "tts": GEMINI_TTS_MODEL,
        },
        "image_provider": settings["image_provider"],
        "local_services": local_status,
        "image_style": LOCAL_STYLE_PREFIX if settings["image_provider"] == "local_sd" else ANIME_WATERCOLOR_STYLE,
    }


@app.get("/api/settings")
def get_settings():
    return db.get_app_settings()


@app.put("/api/settings")
def save_settings(req: AppSettingsUpdateRequest):
    updates = req.model_dump(exclude_none=True)
    return db.update_app_settings(updates)


@app.get("/api/local-image/health")
def check_local_image_services():
    settings = db.get_app_settings()
    return local_image_service.check_services(settings)


@app.get("/api/voices")
def get_voices():
    return VOICE_OPTIONS


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------
@app.get("/api/projects")
def list_all_projects():
    items = db.list_projects()
    return [_enrich_project(p) for p in items]


@app.post("/api/projects")
def create_new_project(req: ProjectCreateRequest):
    proj = db.create_project(
        title=req.title or "",
        language=req.language,
        genre=req.genre,
        target_length_min=req.target_length_min,
        target_duration_sec=req.target_duration_sec,
    )
    return _enrich_project(proj)


@app.get("/api/projects/{project_id}")
def get_single_project(project_id: str):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    return _enrich_project(proj)


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, req: ProjectUpdateRequest):
    if not db.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    updates = req.model_dump(exclude_none=True)
    proj = db.update_project(project_id, updates)
    return _enrich_project(proj)


@app.delete("/api/projects/{project_id}")
def remove_project(project_id: str):
    if not db.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    proj_dir = PROJECTS_DIR / project_id
    if proj_dir.exists():
        shutil.rmtree(proj_dir, ignore_errors=True)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Step 2: Topics
# ---------------------------------------------------------------------------
@app.post("/api/projects/{project_id}/topics")
def generate_project_topics(project_id: str):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    topics = gemini_service.generate_topics(
        language=proj["language"],
        genre=proj["genre"],
        target_length_min=proj["target_length_min"],
        target_duration_sec=proj.get("target_duration_sec"),
    )
    updated = db.update_project(project_id, {"topics": topics, "current_step": max(2, proj["current_step"])})
    return _enrich_project(updated)


@app.post("/api/projects/{project_id}/topics/select")
def select_project_topic(project_id: str, req: TopicSelectRequest):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    clean_topic = req.title.strip()
    if not clean_topic:
        raise HTTPException(status_code=400, detail="Topic title cannot be empty.")

    updates: Dict[str, Any] = {
        "selected_topic": clean_topic,
        "selected_hook": req.hook.strip(),
        "current_step": max(3, proj["current_step"]),
    }
    if not proj.get("title") or proj["title"].startswith("Untitled"):
        updates["title"] = clean_topic[:80]

    updated = db.update_project(project_id, updates)
    return _enrich_project(updated)


# ---------------------------------------------------------------------------
# Step 3: Script
# ---------------------------------------------------------------------------
@app.post("/api/projects/{project_id}/script/generate")
def generate_project_script(project_id: str):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not proj.get("selected_topic"):
        raise HTTPException(status_code=400, detail="Please select a topic before generating a script.")

    script = gemini_service.generate_script(
        language=proj["language"],
        genre=proj["genre"],
        target_length_min=proj["target_length_min"],
        topic=proj["selected_topic"],
        hook=proj.get("selected_hook", ""),
        target_duration_sec=proj.get("target_duration_sec"),
    )
    updated = db.update_project(project_id, {"script": script, "current_step": max(3, proj["current_step"])})
    return _enrich_project(updated)


# ---------------------------------------------------------------------------
# Step 4: Scenes & Character Bible
# ---------------------------------------------------------------------------
@app.post("/api/projects/{project_id}/scenes/generate")
def generate_project_scenes(project_id: str):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not proj.get("script", "").strip():
        raise HTTPException(status_code=400, detail="Please create or save a script first.")

    result = gemini_service.generate_scenes(
        language=proj["language"],
        genre=proj["genre"],
        target_length_min=proj["target_length_min"],
        script=proj["script"],
        target_duration_sec=proj.get("target_duration_sec"),
    )
    db.update_project(
        project_id,
        {
            "character_bible": result["character_bible"],
            "current_step": max(4, proj["current_step"]),
        },
    )
    db.replace_scenes(project_id, result["scenes"])
    return _enrich_project(db.get_project(project_id))


@app.put("/api/projects/{project_id}/scenes")
def bulk_save_scenes(project_id: str, req: ScenesBulkUpdateRequest):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    existing_by_idx = {s["scene_index"]: s for s in proj.get("scenes", [])}
    merged: List[Dict[str, Any]] = []
    for idx, sc in enumerate(req.scenes, start=1):
        prev = existing_by_idx.get(sc.scene_index, {})
        merged.append(
            {
                "scene_index": idx,
                "narration": sc.narration,
                "image_prompt": gemini_service.sanitize_image_prompt(sc.image_prompt),
                "audio_path": prev.get("audio_path", ""),
                "audio_duration_sec": prev.get("audio_duration_sec", 0.0),
                "tts_provider": prev.get("tts_provider", ""),
                "image_path": prev.get("image_path", ""),
            }
        )

    if req.character_bible is not None:
        db.update_project(
            project_id,
            {"character_bible": gemini_service.sanitize_image_prompt(req.character_bible)},
        )
    db.replace_scenes(project_id, merged)
    return _enrich_project(db.get_project(project_id))


@app.patch("/api/projects/{project_id}/scenes/{scene_index}")
def patch_single_scene(project_id: str, scene_index: int, req: SceneUpdateRequest):
    scene = db.get_scene(project_id, scene_index)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found.")
    updates = req.model_dump(exclude_none=True)
    if "image_prompt" in updates:
        updates["image_prompt"] = gemini_service.sanitize_image_prompt(updates["image_prompt"])
    db.update_scene(project_id, scene_index, updates)
    return _enrich_project(db.get_project(project_id))


@app.post("/api/projects/{project_id}/scenes/{scene_index}/regenerate")
def regenerate_scene_text(project_id: str, scene_index: int):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    scenes = proj.get("scenes", [])
    target = next((s for s in scenes if s["scene_index"] == scene_index), None)
    if not target:
        raise HTTPException(status_code=404, detail="Scene not found.")

    prev_s = next((s["narration"] for s in scenes if s["scene_index"] == scene_index - 1), "")
    next_s = next((s["narration"] for s in scenes if s["scene_index"] == scene_index + 1), "")

    regen = gemini_service.regenerate_single_scene(
        language=proj["language"],
        character_bible=proj.get("character_bible", ""),
        current_narration=target["narration"],
        current_image_prompt=target["image_prompt"],
        prev_narration=prev_s,
        next_narration=next_s,
    )
    db.update_scene(project_id, scene_index, regen)
    return _enrich_project(db.get_project(project_id))


# ---------------------------------------------------------------------------
# Step 5: Voiceover (Gemini TTS + edge-tts fallback)
# ---------------------------------------------------------------------------
@app.post("/api/voice/preview")
def preview_voice(req: VoicePreviewRequest):
    out_file = PREVIEW_DIR / f"preview_{req.language}_{req.voice_id}_{uuid.uuid4().hex[:6]}.wav"
    try:
        path, duration, provider = tts_service.synthesize_voice_preview(
            req.language, req.voice_id, out_file
        )
        return {
            "audio_url": _to_media_url(str(path)),
            "duration_sec": duration,
            "provider": provider,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Voice preview failed: {exc}")


def _voiceover_worker(project_id: str, voice_id: str, force_regenerate: bool) -> None:
    try:
        proj = db.get_project(project_id)
        if not proj:
            raise ValueError("Project not found.")
        dirs = db.ensure_project_dirs(project_id)
        scenes = proj.get("scenes", [])
        total = len(scenes)
        if total == 0:
            raise ValueError("No scenes available. Generate scenes in Step 4 first.")

        db.update_project(project_id, {"voice_id": voice_id, "current_step": max(5, proj["current_step"])})
        _set_task(
            project_id,
            "voiceover",
            status="running",
            progress=0,
            completed_items=0,
            total_items=total,
            message=f"Starting voiceover generation for {total} scenes...",
            error=None,
        )

        for idx, sc in enumerate(scenes, start=1):
            if _is_cancelled(project_id, "voiceover"):
                raise TaskCancelledError()
            scene_num = sc["scene_index"]
            out_wav = dirs["audio"] / f"scene_{scene_num:03d}.wav"
            existing_ok = (
                not force_regenerate
                and sc.get("audio_path")
                and Path(sc["audio_path"]).exists()
                and float(sc.get("audio_duration_sec") or 0.0) > 0.1
            )
            if not existing_ok:
                _set_task(
                    project_id,
                    "voiceover",
                    message=f"Synthesizing audio for scene {scene_num}/{total}...",
                )
                wav_path, dur, provider = tts_service.synthesize_speech(
                    text=sc["narration"],
                    language=proj["language"],
                    voice_id=voice_id,
                    output_path=out_wav,
                )
                db.update_scene(
                    project_id,
                    scene_num,
                    {
                        "audio_path": str(wav_path),
                        "audio_duration_sec": dur,
                        "tts_provider": provider,
                    },
                )

            _set_task(
                project_id,
                "voiceover",
                completed_items=idx,
                progress=int((idx / total) * 100),
                message=f"Completed voiceover {idx}/{total}",
            )

        _set_task(
            project_id,
            "voiceover",
            status="completed",
            progress=100,
            completed_items=total,
            total_items=total,
            cancel_requested=False,
            message="All scene voiceovers are ready!",
            error=None,
        )
    except TaskCancelledError:
        logger.info("Voiceover batch cancelled for %s", project_id)
        _set_task(
            project_id,
            "voiceover",
            status="cancelled",
            cancel_requested=False,
            message="Voiceover generation stopped. Completed scenes were saved — click Generate Remaining to continue.",
            error=None,
        )
    except Exception as exc:
        logger.exception("Voiceover batch failed for %s", project_id)
        _set_task(
            project_id,
            "voiceover",
            status="failed",
            cancel_requested=False,
            message="Voiceover generation stopped due to an error.",
            error=str(exc),
        )


@app.post("/api/projects/{project_id}/voiceover/generate-all")
def start_voiceover_batch(project_id: str, req: VoiceBatchRequest, background_tasks: BackgroundTasks):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not proj.get("scenes"):
        raise HTTPException(status_code=400, detail="Generate scenes first before voiceover.")
    if _get_task(project_id, "voiceover")["status"] == "running":
        raise HTTPException(status_code=409, detail="Voiceover generation is already running.")

    _reset_cancel(project_id, "voiceover")
    _set_task(
        project_id,
        "voiceover",
        status="running",
        progress=0,
        completed_items=0,
        total_items=len(proj["scenes"]),
        cancel_requested=False,
        message="Queued voiceover generation...",
        error=None,
    )
    background_tasks.add_task(_voiceover_worker, project_id, req.voice_id, req.force_regenerate)
    return _get_task(project_id, "voiceover")


@app.post("/api/projects/{project_id}/scenes/{scene_index}/voiceover")
def regenerate_scene_voiceover(project_id: str, scene_index: int, req: VoiceBatchRequest):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    scene = db.get_scene(project_id, scene_index)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found.")

    dirs = db.ensure_project_dirs(project_id)
    out_wav = dirs["audio"] / f"scene_{scene_index:03d}.wav"
    wav_path, dur, provider = tts_service.synthesize_speech(
        text=scene["narration"],
        language=proj["language"],
        voice_id=req.voice_id,
        output_path=out_wav,
    )
    db.update_scene(
        project_id,
        scene_index,
        {
            "audio_path": str(wav_path),
            "audio_duration_sec": dur,
            "tts_provider": provider,
        },
    )
    return _enrich_project(db.get_project(project_id))


# ---------------------------------------------------------------------------
# Step 6: Images (Local SD 1.5 + Upscayl or Gemini API Fallback)
# ---------------------------------------------------------------------------
def _generate_image_with_provider(
    provider: str,
    scene_prompt: str,
    character_bible: str,
    output_path: Path,
    seed: Optional[int],
    settings: Dict[str, Any],
    stage_cb=None,
    status_msg_cb=None,
) -> tuple[Path, Optional[int], Optional[str]]:
    if provider == "gemini":
        if stage_cb:
            stage_cb("generating")
        full_prompt = gemini_service.build_full_image_prompt(scene_prompt, character_bible)
        path = gemini_service.generate_image(full_prompt, output_path)
        return path, seed, None

    return local_image_service.generate_and_upscale_scene(
        scene_prompt=scene_prompt,
        character_bible=character_bible,
        out_path=output_path,
        seed=seed,
        settings=settings,
        stage_cb=stage_cb,
        status_msg_cb=status_msg_cb,
    )


def _images_worker(
    project_id: str,
    force_regenerate: bool,
    provider_override: Optional[str] = None,
    test_one: bool = False,
) -> None:
    try:
        proj = db.get_project(project_id)
        if not proj:
            raise ValueError("Project not found.")
        dirs = db.ensure_project_dirs(project_id)
        scenes = proj.get("scenes", [])
        total = len(scenes)
        if total == 0:
            raise ValueError("No scenes available.")

        settings = db.get_app_settings()
        chosen_provider = (provider_override or settings["image_provider"] or "local_sd").lower()
        if chosen_provider == "local_sd":
            svc_health = local_image_service.check_services(settings)
            if not svc_health["fastsd_ok"] and not svc_health.get("auto_start_available"):
                raise LocalImageServiceError(svc_health["fastsd_message"], status_code=400)

        provider_label = (
            "FastSD CPU + Upscayl" if chosen_provider == "local_sd" else "Gemini Image API"
        )

        # Build initial per-scene status map
        scene_statuses: Dict[str, str] = {}
        pending_scenes: List[Dict[str, Any]] = []
        for sc in scenes:
            s_idx = sc["scene_index"]
            exists = bool(sc.get("image_path") and Path(sc["image_path"]).exists())
            if not force_regenerate and exists:
                scene_statuses[str(s_idx)] = "done"
            else:
                scene_statuses[str(s_idx)] = "queued"
                pending_scenes.append(sc)

        if test_one:
            target_list = pending_scenes[:1] if pending_scenes else scenes[:1]
            # If re-testing Scene 1 even if it exists, mark it queued
            if target_list:
                scene_statuses[str(target_list[0]["scene_index"])] = "queued"
        else:
            target_list = pending_scenes

        db.update_project(project_id, {"current_step": max(6, proj["current_step"])})
        total_to_run = len(target_list)
        done_already = sum(1 for v in scene_statuses.values() if v == "done")

        _set_task(
            project_id,
            "images",
            status="running",
            progress=int((done_already / total) * 100),
            completed_items=done_already,
            total_items=total,
            eta_seconds=None,
            scene_statuses=dict(scene_statuses),
            message=(
                f"Testing 1 scene via {provider_label}..."
                if test_one
                else f"Starting {total_to_run} scene(s) sequentially via {provider_label}..."
            ),
            error=None,
        )

        bible = proj.get("character_bible", "")
        durations: List[float] = []

        for run_idx, sc in enumerate(target_list):
            if _is_cancelled(project_id, "images"):
                raise TaskCancelledError()
            scene_num = sc["scene_index"]
            out_png = dirs["images"] / f"scene_{scene_num:03d}.png"
            t0 = time.monotonic()

            def on_stage(stage: str) -> None:
                if _is_cancelled(project_id, "images"):
                    raise TaskCancelledError()
                scene_statuses[str(scene_num)] = stage
                done_count = sum(1 for v in scene_statuses.values() if v == "done")
                _set_task(
                    project_id,
                    "images",
                    scene_statuses=dict(scene_statuses),
                    completed_items=done_count,
                    message=f"Scene {scene_num}/{total}: {stage} ({provider_label})...",
                )

            try:
                existing_seed = sc.get("image_seed")
                img_path, used_seed, warn_msg = _generate_image_with_provider(
                    provider=chosen_provider,
                    scene_prompt=sc["image_prompt"],
                    character_bible=bible,
                    output_path=out_png,
                    seed=existing_seed,
                    settings=settings,
                    stage_cb=on_stage,
                    status_msg_cb=lambda m: _set_task(project_id, "images", message=m),
                )
                if warn_msg:
                    _set_task(project_id, "images", warning=warn_msg)
                db.update_scene(
                    project_id,
                    scene_num,
                    {"image_path": str(img_path), "image_seed": used_seed},
                )
                scene_statuses[str(scene_num)] = "done"
            except TaskCancelledError:
                raise
            except Exception:
                scene_statuses[str(scene_num)] = "error"
                _set_task(project_id, "images", scene_statuses=dict(scene_statuses))
                raise

            elapsed = time.monotonic() - t0
            durations.append(elapsed)
            avg_sec = sum(durations) / len(durations)
            remaining_count = total_to_run - (run_idx + 1)
            eta_sec = int(round(avg_sec * remaining_count)) if remaining_count > 0 else 0

            done_count = sum(1 for v in scene_statuses.values() if v == "done")
            _set_task(
                project_id,
                "images",
                completed_items=done_count,
                progress=100 if test_one else int((done_count / total) * 100),
                eta_seconds=eta_sec,
                scene_statuses=dict(scene_statuses),
                message=(
                    f"Test image Scene {scene_num} ready in {elapsed:.1f}s!"
                    if test_one
                    else f"Completed Scene {scene_num} ({done_count}/{total})"
                ),
            )

        _set_task(
            project_id,
            "images",
            status="completed",
            progress=100 if (test_one or sum(1 for v in scene_statuses.values() if v == "done") == total) else int((sum(1 for v in scene_statuses.values() if v == "done") / total) * 100),
            completed_items=sum(1 for v in scene_statuses.values() if v == "done"),
            total_items=total,
            eta_seconds=0,
            cancel_requested=False,
            scene_statuses=dict(scene_statuses),
            message=(
                "Test image finished! Review quality before generating all scenes."
                if test_one
                else "All scene illustrations are complete!"
            ),
            error=None,
        )
    except TaskCancelledError:
        logger.info("Image batch cancelled for %s", project_id)
        for k, v in list(scene_statuses.items()):
            if v != "done":
                scene_statuses[k] = "queued"
        done_count = sum(1 for v in scene_statuses.values() if v == "done")
        _set_task(
            project_id,
            "images",
            status="cancelled",
            completed_items=done_count,
            progress=int((done_count / total) * 100) if total else 0,
            eta_seconds=None,
            cancel_requested=False,
            scene_statuses=dict(scene_statuses),
            message=f"Image generation stopped ({done_count}/{total} scenes saved). Click Generate Remaining to resume.",
            error=None,
        )
    except Exception as exc:
        logger.exception("Image batch failed for %s", project_id)
        _set_task(
            project_id,
            "images",
            status="failed",
            eta_seconds=None,
            cancel_requested=False,
            message="Image generation stopped due to an error.",
            error=getattr(exc, "message", str(exc)),
        )


@app.post("/api/projects/{project_id}/images/generate-all")
def start_images_batch(project_id: str, req: ImagesBatchRequest, background_tasks: BackgroundTasks):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not proj.get("scenes"):
        raise HTTPException(status_code=400, detail="No scenes found.")
    if _get_task(project_id, "images")["status"] == "running":
        raise HTTPException(status_code=409, detail="Image generation is already running.")

    _reset_cancel(project_id, "images")
    _set_task(
        project_id,
        "images",
        status="running",
        progress=0,
        completed_items=0,
        total_items=len(proj["scenes"]),
        eta_seconds=None,
        warning=None,
        cancel_requested=False,
        scene_statuses={str(s["scene_index"]): "queued" for s in proj["scenes"]},
        message="Checking image services and queuing scenes...",
        error=None,
    )
    background_tasks.add_task(
        _images_worker,
        project_id,
        req.force_regenerate,
        req.provider,
        req.test_one,
    )
    return _get_task(project_id, "images")


@app.post("/api/projects/{project_id}/scenes/{scene_index}/image")
def regenerate_single_image(
    project_id: str,
    scene_index: int,
    req: Optional[SingleImageRegenRequest] = Body(default=None),
):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    scene = db.get_scene(project_id, scene_index)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found.")

    settings = db.get_app_settings()
    chosen_provider = ((req.provider if req else None) or settings["image_provider"] or "local_sd").lower()
    if chosen_provider == "local_sd":
        svc_health = local_image_service.check_services(settings)
        if not svc_health["fastsd_ok"] and not svc_health.get("auto_start_available"):
            raise HTTPException(status_code=400, detail=svc_health["fastsd_message"])

    seed_to_use: Optional[int]
    if req and req.new_seed:
        seed_to_use = random.randint(100_000, 2_000_000_000)
    else:
        seed_to_use = scene.get("image_seed")

    dirs = db.ensure_project_dirs(project_id)
    out_png = dirs["images"] / f"scene_{scene_index:03d}.png"
    img_path, used_seed, warn_msg = _generate_image_with_provider(
        provider=chosen_provider,
        scene_prompt=scene["image_prompt"],
        character_bible=proj.get("character_bible", ""),
        output_path=out_png,
        seed=seed_to_use,
        settings=settings,
    )
    db.update_scene(
        project_id,
        scene_index,
        {"image_path": str(img_path), "image_seed": used_seed},
    )
    enriched = _enrich_project(db.get_project(project_id))
    if enriched is not None and warn_msg:
        enriched["upscale_warning"] = warn_msg
    return enriched


@app.post("/api/projects/{project_id}/images/placeholders")
def generate_placeholder_images(project_id: str):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    scenes = proj.get("scenes", [])
    if not scenes:
        raise HTTPException(status_code=400, detail="No scenes found.")
    dirs = db.ensure_project_dirs(project_id)
    for sc in scenes:
        idx = sc["scene_index"]
        if not sc.get("image_path") or not Path(sc["image_path"]).exists():
            out_png = dirs["images"] / f"scene_{idx:03d}.png"
            gemini_service.generate_placeholder_watercolor_image(idx, out_png)
            db.update_scene(project_id, idx, {"image_path": str(out_png)})
    db.update_project(project_id, {"current_step": max(6, proj["current_step"])})
    return _enrich_project(db.get_project(project_id))


@app.post("/api/projects/{project_id}/scenes/{scene_index}/image-upload")
async def upload_single_scene_image(
    project_id: str,
    scene_index: int,
    file: UploadFile = File(...),
):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    scene = db.get_scene(project_id, scene_index)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found.")

    dirs = db.ensure_project_dirs(project_id)
    out_png = dirs["images"] / f"scene_{scene_index:03d}.png"
    tmp_upload = dirs["images"] / f"upload_{scene_index:03d}_{uuid.uuid4().hex[:6]}"
    raw_bytes = await file.read()
    tmp_upload.write_bytes(raw_bytes)
    try:
        local_image_service._fit_1920x1080_lanczos(tmp_upload, out_png)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}")
    finally:
        tmp_upload.unlink(missing_ok=True)

    db.update_scene(project_id, scene_index, {"image_path": str(out_png)})
    return _enrich_project(db.get_project(project_id))


# ---------------------------------------------------------------------------
# Step 7: Background Music & Video Render
# ---------------------------------------------------------------------------
@app.post("/api/projects/{project_id}/bgm")
async def upload_bgm(project_id: str, file: UploadFile = File(...)):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    ext = Path(file.filename or "music.mp3").suffix.lower()
    if ext not in (".mp3", ".wav", ".m4a", ".ogg", ".aac"):
        raise HTTPException(status_code=400, detail="Unsupported audio format. Use MP3, WAV, M4A, or OGG.")

    dirs = db.ensure_project_dirs(project_id)
    # Clear old BGM files
    for old in dirs["bgm"].glob("*"):
        old.unlink(missing_ok=True)

    dest = dirs["bgm"] / f"bgm{ext}"
    content = await file.read()
    dest.write_bytes(content)

    updated = db.update_project(project_id, {"bgm_path": str(dest)})
    return _enrich_project(updated)


@app.delete("/api/projects/{project_id}/bgm")
def delete_bgm(project_id: str):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    dirs = db.ensure_project_dirs(project_id)
    for old in dirs["bgm"].glob("*"):
        old.unlink(missing_ok=True)
    updated = db.update_project(project_id, {"bgm_path": ""})
    return _enrich_project(updated)


def _render_worker(project_id: str, req: VideoRenderRequest) -> None:
    try:
        proj = db.get_project(project_id)
        if not proj:
            raise ValueError("Project not found.")
        dirs = db.ensure_project_dirs(project_id)

        db.update_project(
            project_id,
            {
                "bgm_volume": req.bgm_volume,
                "auto_duck": req.auto_duck,
                "burn_subtitles": req.burn_subtitles,
                "current_step": max(7, proj["current_step"]),
            },
        )
        bgm = Path(proj["bgm_path"]) if proj.get("bgm_path") else None

        def on_progress(pct: int, msg: str) -> None:
            _set_task(
                project_id,
                "render",
                status="running",
                progress=pct,
                message=msg,
                error=None,
            )

        out_filename = "test_preview_15s.mp4" if req.test_preview_15s else "final_video.mp4"
        out_mp4 = video_service.render_project_video(
            project=proj,
            scenes=proj.get("scenes", []),
            render_dir=dirs["render"],
            bgm_path=bgm,
            bgm_volume=req.bgm_volume,
            auto_duck=req.auto_duck,
            burn_subtitles=req.burn_subtitles,
            progress_cb=on_progress,
            max_duration_sec=15.0 if req.test_preview_15s else None,
            output_filename=out_filename,
            cancel_cb=lambda: _is_cancelled(project_id, "render"),
        )
        if not req.test_preview_15s:
            db.update_project(project_id, {"video_path": str(out_mp4), "current_step": max(7, proj["current_step"])})
        _set_task(
            project_id,
            "render",
            status="completed",
            progress=100,
            cancel_requested=False,
            message=(
                "15-second test preview rendered! Watch it below before full export."
                if req.test_preview_15s
                else "Final 1080p MP4 video rendered successfully!"
            ),
            error=None,
        )
    except (video_service.RenderCancelledError, TaskCancelledError):
        logger.info("Render cancelled for %s", project_id)
        _set_task(
            project_id,
            "render",
            status="cancelled",
            cancel_requested=False,
            message="Video render stopped by user.",
            error=None,
        )
    except Exception as exc:
        logger.exception("Render failed for %s", project_id)
        _set_task(
            project_id,
            "render",
            status="failed",
            cancel_requested=False,
            message="Video render failed.",
            error=str(exc),
        )


@app.post("/api/projects/{project_id}/render")
def start_video_render(project_id: str, req: VideoRenderRequest, background_tasks: BackgroundTasks):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    scenes = proj.get("scenes", [])
    if not scenes:
        raise HTTPException(status_code=400, detail="No scenes found.")
    missing_audio = [s["scene_index"] for s in scenes if not s.get("audio_path") or not Path(s["audio_path"]).exists()]
    missing_img = [s["scene_index"] for s in scenes if not s.get("image_path") or not Path(s["image_path"]).exists()]
    if missing_audio:
        raise HTTPException(status_code=400, detail=f"Missing voiceover audio for scenes: {missing_audio[:5]}")
    if missing_img:
        raise HTTPException(status_code=400, detail=f"Missing images for scenes: {missing_img[:5]}")
    if _get_task(project_id, "render")["status"] == "running":
        raise HTTPException(status_code=409, detail="Video render is already in progress.")

    _reset_cancel(project_id, "render")
    _set_task(
        project_id,
        "render",
        status="running",
        progress=1,
        cancel_requested=False,
        message="Initializing video render pipeline...",
        error=None,
    )
    background_tasks.add_task(_render_worker, project_id, req)
    return _get_task(project_id, "render")


@app.get("/api/projects/{project_id}/tasks/{task_type}")
def get_task_status(project_id: str, task_type: str):
    if task_type not in ("voiceover", "images", "render"):
        raise HTTPException(status_code=400, detail="Invalid task type.")
    return _get_task(project_id, task_type)


@app.post("/api/projects/{project_id}/tasks/{task_type}/stop")
def stop_running_task(project_id: str, task_type: str):
    if task_type not in ("voiceover", "images", "render"):
        raise HTTPException(status_code=400, detail="Invalid task type.")
    cur = _get_task(project_id, task_type)
    if cur.get("status") != "running":
        return cur
    _request_cancel(project_id, task_type)
    _set_task(
        project_id,
        task_type,
        cancel_requested=True,
        message="Stopping task right after the active step...",
    )
    return _get_task(project_id, task_type)


# ---------------------------------------------------------------------------
# Step 8: YouTube Package & Thumbnails
# ---------------------------------------------------------------------------
def _compute_chapter_timestamps(scenes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not scenes:
        return [{"time": "00:00", "label": "Story Opening"}]
    timeline = video_service.calculate_scene_timeline(scenes)
    # Select ~5 evenly spaced chapter points across the story
    n = len(timeline)
    indices = sorted({0, max(0, n // 5), max(0, (2 * n) // 5), max(0, (3 * n) // 5), max(0, (4 * n) // 5)})
    chapters = []
    for idx in indices:
        item = timeline[idx]
        snippet = " ".join(item["narration"].split()[:6]).rstrip(".,।!?")
        chapters.append(
            {
                "time": video_service.format_yt_timestamp(item["start_sec"]),
                "label": snippet or f"Chapter {len(chapters) + 1}",
            }
        )
    return chapters


def _write_metadata_txt(proj: Dict[str, Any], yt: Dict[str, Any], out_path: Path) -> None:
    lines = [
        "==================================================",
        f"STORYTUBE STUDIO - YOUTUBE PUBLISHING PACKAGE",
        f"Project: {proj.get('title', '')}",
        f"Language: {proj.get('language', '').upper()} | Genre: {proj.get('genre', '')}",
        "==================================================",
        "",
        "TITLE OPTIONS (All <= 70 characters):",
    ]
    for i, t in enumerate(yt.get("titles", []), start=1):
        lines.append(f"  {i}. {t} ({len(t)} chars)")
    lines.extend(
        [
            "",
            "SEO DESCRIPTION:",
            "--------------------------------------------------",
            yt.get("description", ""),
            "",
            "HASHTAGS:",
            " ".join(yt.get("hashtags", [])),
            "",
            "TAGS (15):",
            ", ".join(yt.get("tags", [])),
            "",
            "THUMBNAIL CONCEPTS:",
        ]
    )
    for i, c in enumerate(yt.get("thumbnail_concepts", []), start=1):
        lines.append(
            f"  {i}. {c.get('concept_title', '')} | Overlay: \"{c.get('overlay_text', '')}\" | Prompt: {c.get('visual_description', '')}"
        )
    out_path.write_text("\n".join(lines), encoding="utf-8")


@app.post("/api/projects/{project_id}/youtube/generate")
def generate_youtube_assets(project_id: str):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not proj.get("script"):
        raise HTTPException(status_code=400, detail="Generate a script first.")

    dirs = db.ensure_project_dirs(project_id)
    scenes = proj.get("scenes", [])
    chapters = _compute_chapter_timestamps(scenes)

    yt_data = gemini_service.generate_youtube_package(
        language=proj["language"],
        genre=proj["genre"],
        topic=proj.get("selected_topic") or proj.get("title", ""),
        script=proj["script"],
        chapter_timestamps=chapters,
    )

    # Generate 3 1280x720 thumbnails using the configured image provider
    settings = db.get_app_settings()
    chosen_provider = settings["image_provider"]
    bible = proj.get("character_bible", "")
    fallback_scene_imgs = [Path(s["image_path"]) for s in scenes if s.get("image_path") and Path(s["image_path"]).exists()]

    for i, concept in enumerate(yt_data["thumbnail_concepts"]):
        raw_bg = dirs["thumbnails"] / f"thumb_bg_{i + 1}.png"
        final_thumb = dirs["thumbnails"] / f"thumbnail_{i + 1}.png"

        try:
            _generate_image_with_provider(
                provider=chosen_provider,
                scene_prompt=concept["visual_description"],
                character_bible=bible,
                output_path=raw_bg,
                seed=5000 + i,
                settings=settings,
            )
            bg_source = raw_bg
        except Exception as exc:
            logger.warning("Thumbnail background %d (%s) failed (%s); using fallback.", i + 1, chosen_provider, exc)
            if fallback_scene_imgs:
                bg_source = fallback_scene_imgs[min(i * max(1, len(fallback_scene_imgs) // 3), len(fallback_scene_imgs) - 1)]
            else:
                bg_source = gemini_service.generate_placeholder_watercolor_image(i + 1, raw_bg)

        thumbnail_service.create_thumbnail(
            background_image_path=bg_source,
            overlay_text=concept["overlay_text"],
            language=proj["language"],
            accent_color=concept.get("accent_color", "#FFD166"),
            output_path=final_thumb,
        )
        concept["image_path"] = str(final_thumb)

    _write_metadata_txt(proj, yt_data, dirs["thumbnails"] / "youtube_metadata.txt")
    updated = db.update_project(
        project_id,
        {"youtube_package": yt_data, "current_step": 8},
    )
    return _enrich_project(updated)


@app.post("/api/projects/{project_id}/youtube/thumbnail")
def regenerate_single_thumbnail(project_id: str, req: ThumbnailRegenerateRequest):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    yt_data = proj.get("youtube_package") or {}
    concepts = yt_data.get("thumbnail_concepts", [])
    if req.concept_index >= len(concepts):
        raise HTTPException(status_code=404, detail="Thumbnail concept not found.")

    dirs = db.ensure_project_dirs(project_id)
    concept = concepts[req.concept_index]
    if req.overlay_text is not None:
        concept["overlay_text"] = req.overlay_text.strip()
    if req.visual_description is not None:
        concept["visual_description"] = req.visual_description.strip()

    raw_bg = dirs["thumbnails"] / f"thumb_bg_{req.concept_index + 1}.png"
    final_thumb = dirs["thumbnails"] / f"thumbnail_{req.concept_index + 1}.png"

    if req.source_scene_index:
        sc = db.get_scene(project_id, req.source_scene_index)
        if not sc or not sc.get("image_path") or not Path(sc["image_path"]).exists():
            raise HTTPException(status_code=400, detail="Selected scene image does not exist.")
        bg_source = Path(sc["image_path"])
    elif req.use_fresh_ai_bg or not raw_bg.exists():
        settings = db.get_app_settings()
        _generate_image_with_provider(
            provider=settings["image_provider"],
            scene_prompt=concept["visual_description"],
            character_bible=proj.get("character_bible", ""),
            output_path=raw_bg,
            seed=random.randint(100_000, 2_000_000_000),
            settings=settings,
        )
        bg_source = raw_bg
    else:
        bg_source = raw_bg

    thumbnail_service.create_thumbnail(
        background_image_path=bg_source,
        overlay_text=concept["overlay_text"],
        language=proj["language"],
        accent_color=concept.get("accent_color", "#FFD166"),
        output_path=final_thumb,
    )
    concept["image_path"] = str(final_thumb)
    _write_metadata_txt(proj, yt_data, dirs["thumbnails"] / "youtube_metadata.txt")
    updated = db.update_project(project_id, {"youtube_package": yt_data})
    return _enrich_project(updated)


@app.get("/api/projects/{project_id}/download/{asset_type}")
def download_asset(project_id: str, asset_type: str):
    proj = db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    dirs = db.ensure_project_dirs(project_id)
    if asset_type == "video":
        path = Path(proj.get("video_path") or dirs["render"] / "final_video.mp4")
        filename = f"storytube_{project_id}.mp4"
    elif asset_type == "metadata":
        path = dirs["thumbnails"] / "youtube_metadata.txt"
        filename = f"youtube_metadata_{project_id}.txt"
    elif asset_type in ("thumbnail_1", "thumbnail_2", "thumbnail_3"):
        path = dirs["thumbnails"] / f"{asset_type}.png"
        filename = f"{asset_type}_{project_id}.png"
    else:
        raise HTTPException(status_code=400, detail="Invalid asset type.")

    if not path.exists():
        raise HTTPException(status_code=404, detail="Requested file has not been generated yet.")
    return FileResponse(path=str(path), filename=filename, media_type="application/octet-stream")
