import React, { useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Loader2,
  Mic,
  RefreshCw,
  Square,
  Volume2,
} from "lucide-react";
import { api } from "../../api/client";

export default function Step5Voiceover({
  project,
  voices,
  onRefreshProject,
  onError,
  onProceedToImages,
}) {
  const langVoices = voices?.[project?.language] || [];
  const [selectedVoice, setSelectedVoice] = useState(
    project?.voice_id || langVoices[0]?.id || "Aoede"
  );
  const [previewing, setPreviewing] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewProvider, setPreviewProvider] = useState("");
  const [task, setTask] = useState({ status: "idle", progress: 0, message: "" });
  const [regenSceneIdx, setRegenSceneIdx] = useState(null);
  const [cacheBust, setCacheBust] = useState(Date.now());

  const scenes = project?.scenes || [];
  const completedCount = scenes.filter((s) => Boolean(s.audio_url)).length;
  const allDone = scenes.length > 0 && completedCount === scenes.length;

  useEffect(() => {
    if (project?.voice_id) {
      setSelectedVoice(project.voice_id);
    } else if (langVoices.length > 0) {
      setSelectedVoice(langVoices[0].id);
    }
  }, [project?.voice_id, langVoices]);

  // Check if a batch task is already running on load
  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const st = await api.getTaskStatus(project.id, "voiceover");
        if (!active) return;
        setTask(st);
        if (st.status === "running") {
          await onRefreshProject();
        }
      } catch {
        // ignore transient poll errors
      }
    };
    poll();
    const timer = setInterval(() => {
      if (task.status === "running") {
        poll().then(() => setCacheBust(Date.now()));
      }
    }, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [project.id, task.status, onRefreshProject]);

  // Refresh once when transitioning to completed or cancelled
  useEffect(() => {
    if (task.status === "completed" || task.status === "cancelled") {
      onRefreshProject();
      setCacheBust(Date.now());
    } else if (task.status === "failed" && task.error) {
      onError(task.error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.status]);

  const handleStopTask = async () => {
    onError("");
    try {
      const st = await api.stopTask(project.id, "voiceover");
      setTask(st);
    } catch (err) {
      onError(err.message);
    }
  };

  const handlePreview = async () => {
    setPreviewing(true);
    onError("");
    try {
      const res = await api.previewVoice({
        language: project.language,
        voice_id: selectedVoice,
      });
      setPreviewUrl(res.audio_url);
      setPreviewProvider(res.provider);
    } catch (err) {
      onError(err.message);
    } finally {
      setPreviewing(false);
    }
  };

  const handleStartBatch = async (force = false) => {
    onError("");
    try {
      const st = await api.startVoiceoverBatch(project.id, {
        voice_id: selectedVoice,
        force_regenerate: force,
      });
      setTask(st);
    } catch (err) {
      onError(err.message);
    }
  };

  const handleRegenOne = async (sceneIndex) => {
    setRegenSceneIdx(sceneIndex);
    onError("");
    try {
      await api.regenerateSceneVoiceover(project.id, sceneIndex, {
        voice_id: selectedVoice,
        force_regenerate: true,
      });
      await onRefreshProject();
      setCacheBust(Date.now());
    } catch (err) {
      onError(err.message);
    } finally {
      setRegenSceneIdx(null);
    }
  };

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
            Step 5 of 8
          </span>
          <h2 className="mt-1 text-2xl font-bold text-white">
            Generate Per-Scene Voiceovers ({completedCount}/{scenes.length})
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Uses Gemini TTS with automatic edge-tts fallback. One WAV file per scene guarantees exact subtitle and image sync.
          </p>
        </div>

        <button
          type="button"
          onClick={onProceedToImages}
          disabled={!allDone || task.status === "running"}
          className="inline-flex items-center gap-2 self-start rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500 disabled:opacity-40"
        >
          Next: Generate Images
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>

      {/* Voice Controls Card */}
      <div className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
        <div className="grid gap-4 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-5">
            <label className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Mic className="h-4 w-4 text-indigo-400" />
              Narrator Voice ({project?.language === "hindi" ? "Hindi" : "English"})
            </label>
            <select
              value={selectedVoice}
              onChange={(e) => setSelectedVoice(e.target.value)}
              disabled={task.status === "running"}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white focus:border-indigo-500 focus:outline-none"
            >
              {langVoices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-wrap gap-2.5 lg:col-span-7 lg:justify-end">
            <button
              type="button"
              onClick={handlePreview}
              disabled={previewing || task.status === "running"}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-indigo-500 hover:text-white disabled:opacity-50"
            >
              {previewing ? (
                <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
              ) : (
                <Volume2 className="h-4 w-4 text-indigo-400" />
              )}
              Preview Voice
            </button>

            <button
              type="button"
              onClick={() => handleStartBatch(false)}
              disabled={task.status === "running" || allDone}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {task.status === "running" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Mic className="h-4 w-4" />
              )}
              {completedCount > 0 && !allDone
                ? `Generate Remaining (${scenes.length - completedCount})`
                : "Generate All Voiceovers"}
            </button>

            {completedCount > 0 && (
              <button
                type="button"
                onClick={() => handleStartBatch(true)}
                disabled={task.status === "running"}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:bg-slate-700 disabled:opacity-50"
              >
                <RefreshCw className="h-4 w-4" />
                Regenerate All
              </button>
            )}
          </div>
        </div>

        {previewUrl && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-2.5">
            <span className="text-xs font-semibold text-indigo-300">
              Voice Preview ({previewProvider}):
            </span>
            <audio controls autoPlay src={previewUrl} className="h-9 max-w-md flex-1" />
          </div>
        )}

        {task.status === "running" && (
          <div className="mt-4">
            <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="font-medium text-indigo-300">{task.message}</span>
              <div className="flex items-center gap-3">
                <span className="font-bold text-white">
                  {task.progress}% ({task.completed_items}/{task.total_items})
                </span>
                <button
                  type="button"
                  onClick={handleStopTask}
                  disabled={task.cancel_requested}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/50 bg-rose-500/15 px-3 py-1 text-xs font-bold text-rose-200 transition hover:bg-rose-500/25 disabled:opacity-50"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                  {task.cancel_requested ? "Stopping..." : "Stop"}
                </button>
              </div>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-300"
                style={{ width: `${task.progress}%` }}
              />
            </div>
          </div>
        )}

        {task.status === "cancelled" && (
          <div className="mt-4 rounded-xl border border-amber-500/40 bg-amber-950/30 px-4 py-2.5 text-xs text-amber-200">
            {task.message || "Voiceover generation stopped. Completed scenes were saved — click Generate Remaining to continue."}
          </div>
        )}
      </div>

      {/* Scene Audio List */}
      <div className="space-y-3">
        {scenes.map((sc) => (
          <div
            key={sc.scene_index}
            className="flex flex-col justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4 sm:flex-row sm:items-center"
          >
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs font-bold text-indigo-300">
                  Scene {sc.scene_index}
                </span>
                {sc.audio_url ? (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {Number(sc.audio_duration_sec || 0).toFixed(1)}s · {sc.tts_provider}
                  </span>
                ) : (
                  <span className="text-xs text-slate-500">Pending audio</span>
                )}
              </div>
              <p className="text-sm text-slate-200">{sc.narration}</p>
            </div>

            <div className="flex shrink-0 items-center gap-2.5">
              {sc.audio_url && (
                <audio
                  controls
                  src={`${sc.audio_url}?t=${cacheBust}`}
                  className="h-9 w-56"
                />
              )}
              <button
                type="button"
                onClick={() => handleRegenOne(sc.scene_index)}
                disabled={regenSceneIdx === sc.scene_index || task.status === "running"}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-semibold text-slate-300 transition hover:border-indigo-500 hover:text-white disabled:opacity-50"
              >
                {regenSceneIdx === sc.scene_index ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                Regenerate
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
