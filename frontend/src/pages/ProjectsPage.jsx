import React, { useEffect, useState } from "react";
import {
  Clock,
  Film,
  Image as ImageIcon,
  Languages,
  Mic,
  Play,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import { api } from "../api/client";
import ErrorBanner from "../components/ErrorBanner";

const GENRE_BADGES = {
  moral_stories: "Moral Stories",
  kids: "Kids & Bedtime",
  mythology: "Mythology",
  mystery: "Mystery",
  horror: "Horror Stories",
};

const STEP_NAMES = [
  "",
  "Setup",
  "Topics",
  "Script",
  "Scenes",
  "Voiceover",
  "Images",
  "Render",
  "YouTube Package",
];

export default function ProjectsPage({ onOpenProject, onCreateNew }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState(null);

  const loadProjects = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.listProjects();
      setProjects(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    if (!window.confirm("Delete this project and all its generated audio, images, and video files?")) {
      return;
    }
    setDeletingId(id);
    try {
      await api.deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Your Story Projects
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Every step auto-saves locally to SQLite and disk. Resume any video right where you left off.
          </p>
        </div>
        <button
          onClick={onCreateNew}
          className="inline-flex items-center gap-2 self-start rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500"
        >
          <Plus className="h-4 w-4" />
          Create New Story Video
        </button>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError("")} />

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-48 animate-pulse rounded-2xl border border-slate-800 bg-slate-900/60"
            />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 px-6 py-16 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-500/15 text-indigo-400">
            <Sparkles className="h-7 w-7" />
          </div>
          <h2 className="text-lg font-semibold text-white">No story videos yet</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-400">
            Start a new project to generate trending story topics, a full 10-minute script,
            hand-painted anime watercolor scenes, voiceovers, and a ready-to-upload MP4.
          </p>
          <button
            onClick={onCreateNew}
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500"
          >
            <Plus className="h-4 w-4" />
            Start Your First Video
          </button>
        </div>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => {
            const stepName = STEP_NAMES[p.current_step] || "Setup";
            const updatedDate = new Date(p.updated_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            });

            return (
              <div
                key={p.id}
                onClick={() => onOpenProject(p.id)}
                className="group relative flex cursor-pointer flex-col justify-between rounded-2xl border border-slate-800 bg-slate-900/70 p-5 transition hover:border-indigo-500/50 hover:bg-slate-900"
              >
                <div>
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-xs font-semibold text-indigo-300">
                      Step {p.current_step}/8 · {stepName}
                    </span>
                    <button
                      onClick={(e) => handleDelete(e, p.id)}
                      disabled={deletingId === p.id}
                      className="rounded-lg p-1.5 text-slate-500 transition hover:bg-rose-500/15 hover:text-rose-400"
                      title="Delete project"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>

                  <h3 className="line-clamp-2 text-lg font-bold text-white group-hover:text-indigo-300">
                    {p.title}
                  </h3>
                  {p.selected_topic && p.selected_topic !== p.title && (
                    <p className="mt-1 line-clamp-1 text-xs text-slate-400">
                      {p.selected_topic}
                    </p>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-300">
                    <span className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1">
                      <Languages className="h-3.5 w-3.5 text-indigo-400" />
                      {p.language === "hindi" ? "Hindi" : "English"}
                    </span>
                    <span className="rounded-md bg-slate-800 px-2 py-1">
                      {GENRE_BADGES[p.genre] || p.genre}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1">
                      <Clock className="h-3.5 w-3.5 text-amber-400" />
                      {p.target_duration_sec === 15 ? "15s Test" : `${p.target_length_min} min`}
                    </span>
                  </div>
                </div>

                <div className="mt-5 border-t border-slate-800/80 pt-3.5">
                  <div className="mb-3 flex items-center justify-between text-xs text-slate-400">
                    <span className="inline-flex items-center gap-1">
                      <Film className="h-3.5 w-3.5" /> {p.scene_count || 0} scenes
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Mic className="h-3.5 w-3.5" /> {p.audio_count || 0} audio
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <ImageIcon className="h-3.5 w-3.5" /> {p.image_count || 0} art
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-slate-500">Updated {updatedDate}</span>
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-400 group-hover:text-indigo-300">
                      <Play className="h-3.5 w-3.5 fill-current" />
                      {p.video_url ? "Open / Download" : "Resume"}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
