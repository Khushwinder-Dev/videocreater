import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    DB_PATH,
    DEFAULT_PROVIDER,
    FASTSD_GUIDANCE,
    FASTSD_STEPS,
    FASTSD_URL,
    PROJECTS_DIR,
    UPSCALE_ENABLED,
    UPSCAYL_BIN,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT 'english',
                genre TEXT NOT NULL DEFAULT 'moral_stories',
                target_length_min INTEGER NOT NULL DEFAULT 10,
                target_duration_sec INTEGER NOT NULL DEFAULT 600,
                current_step INTEGER NOT NULL DEFAULT 1,
                topics_json TEXT NOT NULL DEFAULT '[]',
                selected_topic TEXT NOT NULL DEFAULT '',
                selected_hook TEXT NOT NULL DEFAULT '',
                script TEXT NOT NULL DEFAULT '',
                character_bible TEXT NOT NULL DEFAULT '',
                voice_id TEXT NOT NULL DEFAULT 'Aoede',
                bgm_path TEXT NOT NULL DEFAULT '',
                bgm_volume REAL NOT NULL DEFAULT 0.18,
                auto_duck INTEGER NOT NULL DEFAULT 1,
                burn_subtitles INTEGER NOT NULL DEFAULT 1,
                video_path TEXT NOT NULL DEFAULT '',
                youtube_package_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                scene_index INTEGER NOT NULL,
                narration TEXT NOT NULL,
                image_prompt TEXT NOT NULL,
                audio_path TEXT NOT NULL DEFAULT '',
                audio_duration_sec REAL NOT NULL DEFAULT 0.0,
                tts_provider TEXT NOT NULL DEFAULT '',
                image_path TEXT NOT NULL DEFAULT '',
                image_seed INTEGER,
                UNIQUE(project_id, scene_index),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                image_provider TEXT NOT NULL DEFAULT 'local_sd',
                fastsd_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:8000',
                upscayl_bin TEXT NOT NULL DEFAULT '',
                steps INTEGER NOT NULL DEFAULT 6,
                guidance_scale REAL NOT NULL DEFAULT 1.4,
                upscale_enabled INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        conn.commit()
        # Safe migration for existing databases lacking target_duration_sec / image_seed
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "target_duration_sec" not in cols:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN target_duration_sec INTEGER NOT NULL DEFAULT 600"
            )
            conn.execute(
                "UPDATE projects SET target_duration_sec = MAX(15, target_length_min * 60)"
            )
            conn.commit()

        scene_cols = {row["name"] for row in conn.execute("PRAGMA table_info(scenes)").fetchall()}
        if "image_seed" not in scene_cols:
            conn.execute("ALTER TABLE scenes ADD COLUMN image_seed INTEGER")
            conn.commit()

        # Seed default settings row if missing
        row = conn.execute("SELECT id FROM app_settings WHERE id = 1").fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO app_settings (
                    id, image_provider, fastsd_url, upscayl_bin, steps, guidance_scale, upscale_enabled
                ) VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_PROVIDER,
                    FASTSD_URL,
                    UPSCAYL_BIN,
                    FASTSD_STEPS,
                    FASTSD_GUIDANCE,
                    1 if UPSCALE_ENABLED else 0,
                ),
            )
            conn.commit()
    finally:
        conn.close()


def ensure_project_dirs(project_id: str) -> Dict[str, Path]:
    root = PROJECTS_DIR / project_id
    subdirs = {
        "root": root,
        "audio": root / "audio",
        "images": root / "images",
        "bgm": root / "bgm",
        "render": root / "render",
        "thumbnails": root / "thumbnails",
    }
    for path in subdirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return subdirs


def _row_to_project(row: sqlite3.Row, scenes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    data = dict(row)
    data["topics"] = json.loads(data.pop("topics_json", "[]") or "[]")
    data["youtube_package"] = json.loads(data.pop("youtube_package_json", "{}") or "{}")
    data["auto_duck"] = bool(data.get("auto_duck", 1))
    data["burn_subtitles"] = bool(data.get("burn_subtitles", 1))
    if scenes is not None:
        data["scenes"] = scenes
    return data


def create_project(
    title: str,
    language: str,
    genre: str,
    target_length_min: int,
    target_duration_sec: Optional[int] = None,
) -> Dict[str, Any]:
    project_id = uuid.uuid4().hex[:12]
    ensure_project_dirs(project_id)
    now = _now_iso()
    default_voice = "Kore" if language == "hindi" else "Aoede"
    clean_title = title.strip() or f"Untitled {genre.replace('_', ' ').title()} Story"
    duration_sec = (
        target_duration_sec
        if target_duration_sec is not None
        else max(60, target_length_min * 60)
    )

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO projects (
                id, title, language, genre, target_length_min, target_duration_sec, current_step,
                voice_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                project_id,
                clean_title,
                language,
                genre,
                target_length_min,
                duration_sec,
                default_voice,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_project(project_id)  # type: ignore[return-value]


def list_projects() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.*,
                (SELECT COUNT(*) FROM scenes s WHERE s.project_id = p.id) AS scene_count,
                (SELECT COUNT(*) FROM scenes s WHERE s.project_id = p.id AND s.audio_path != '') AS audio_count,
                (SELECT COUNT(*) FROM scenes s WHERE s.project_id = p.id AND s.image_path != '') AS image_count
            FROM projects p
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
        return [_row_to_project(r) for r in rows]
    finally:
        conn.close()


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        scene_rows = conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_index ASC",
            (project_id,),
        ).fetchall()
        scenes = [dict(s) for s in scene_rows]
        return _row_to_project(row, scenes=scenes)
    finally:
        conn.close()


def update_project(project_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not fields:
        return get_project(project_id)

    payload: Dict[str, Any] = {}
    for k, v in fields.items():
        if k == "topics":
            payload["topics_json"] = json.dumps(v, ensure_ascii=False)
        elif k == "youtube_package":
            payload["youtube_package_json"] = json.dumps(v, ensure_ascii=False)
        elif k in ("auto_duck", "burn_subtitles"):
            payload[k] = 1 if v else 0
        else:
            payload[k] = v

    payload["updated_at"] = _now_iso()
    columns = ", ".join(f"{k} = ?" for k in payload.keys())
    values = list(payload.values()) + [project_id]

    conn = get_connection()
    try:
        conn.execute(f"UPDATE projects SET {columns} WHERE id = ?", values)
        conn.commit()
        # Safe migration for existing databases lacking target_duration_sec
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "target_duration_sec" not in cols:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN target_duration_sec INTEGER NOT NULL DEFAULT 600"
            )
            conn.execute(
                "UPDATE projects SET target_duration_sec = MAX(15, target_length_min * 60)"
            )
            conn.commit()
    finally:
        conn.close()
    return get_project(project_id)


def delete_project(project_id: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def replace_scenes(project_id: str, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM scenes WHERE project_id = ?", (project_id,))
        for idx, s in enumerate(scenes, start=1):
            conn.execute(
                """
                INSERT INTO scenes (
                    project_id, scene_index, narration, image_prompt,
                    audio_path, audio_duration_sec, tts_provider, image_path, image_seed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    idx,
                    s["narration"],
                    s["image_prompt"],
                    s.get("audio_path", ""),
                    float(s.get("audio_duration_sec", 0.0)),
                    s.get("tts_provider", ""),
                    s.get("image_path", ""),
                    s.get("image_seed"),
                ),
            )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now_iso(), project_id))
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_index ASC",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_app_settings() -> Dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM app_settings WHERE id = 1").fetchone()
        if not row:
            return {
                "image_provider": DEFAULT_PROVIDER,
                "fastsd_url": FASTSD_URL,
                "upscayl_bin": UPSCAYL_BIN,
                "steps": FASTSD_STEPS,
                "guidance_scale": FASTSD_GUIDANCE,
                "upscale_enabled": UPSCALE_ENABLED,
            }
        data = dict(row)
        data.pop("id", None)
        data["upscale_enabled"] = bool(data.get("upscale_enabled", 1))
        return data
    finally:
        conn.close()


def update_app_settings(fields: Dict[str, Any]) -> Dict[str, Any]:
    if not fields:
        return get_app_settings()
    payload: Dict[str, Any] = {}
    for k, v in fields.items():
        if k == "upscale_enabled":
            payload[k] = 1 if v else 0
        elif k == "fastsd_url" and isinstance(v, str):
            payload[k] = v.strip().rstrip("/")
        elif k == "upscayl_bin" and isinstance(v, str):
            payload[k] = v.strip().strip('"')
        else:
            payload[k] = v
    columns = ", ".join(f"{k} = ?" for k in payload.keys())
    values = list(payload.values())
    conn = get_connection()
    try:
        conn.execute(f"UPDATE app_settings SET {columns} WHERE id = 1", values)
        conn.commit()
    finally:
        conn.close()
    return get_app_settings()


def update_scene(project_id: str, scene_index: int, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not fields:
        return get_scene(project_id, scene_index)
    columns = ", ".join(f"{k} = ?" for k in fields.keys())
    values = list(fields.values()) + [project_id, scene_index]
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE scenes SET {columns} WHERE project_id = ? AND scene_index = ?",
            values,
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now_iso(), project_id))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? AND scene_index = ?",
            (project_id, scene_index),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_scene(project_id: str, scene_index: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? AND scene_index = ?",
            (project_id, scene_index),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
