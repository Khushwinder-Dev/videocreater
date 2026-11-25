import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Clock,
  Cpu,
  Dices,
  FlaskConical,
  Image as ImageIcon,
  Loader2,
  Palette,
  RefreshCw,
  Sparkles,
  Square,
  Upload,
} from "lucide-react";
import { api } from "../../api/client";

function formatEta(seconds) {
  if (seconds === null || seconds === undefined || seconds <= 0) return "";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return mins > 0 ? `~${mins}m ${secs}s remaining` : `~${secs}s remaining`;
}

const STATUS_BADGE = {
  queued: "bg-slate-800 text-slate-300",
  generating: "bg-indigo-500/20 text-indigo-300 ring-1 ring-indigo-500/40",
  upscaling: "bg-purple-500/20 text-purple-300 ring-1 ring-purple-500/40",
  done: "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40",
  error: "bg-rose-500/20 text-rose-300 ring-1 ring-rose-500/40",
};

export default function Step6Images({
  project,
  onRefreshProject,
  onError,
  onProceedToRender,
}) {
  const [provider, setProvider] = useState("local_sd");
  const [localHealth, setLocalHealth] = useState(null);
  const [task, setTask] = useState({
    status: "idle",
    progress: 0,
    message: "",
    eta_seconds: null,
    scene_statuses: {},
  });
  const [regenIdx, setRegenIdx] = useState(null);
  const [generatingPlaceholders, setGeneratingPlaceholders] = useState(false);
  const [upscaleWarning, setUpscaleWarning] = useState("");
  const [editingPrompt, setEditingPrompt] = useState({});
  const [cacheBust, setCacheBust] = useState(Date.now());

  const scenes = project?.scenes || [];
  const completedCount = scenes.filter((s) => Boolean(s.image_url)).length;
  const allDone = scenes.length > 0 && completedCount === scenes.length;

  useEffect(() => {
    api
      .getSettings()
      .then((cfg) => {
        if (cfg?.image_provider) setProvider(cfg.image_provider);
      })
      .catch(() => {});
    api.checkLocalImageHealth().then(setLocalHealth).catch(() => {});
  }, []);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const st = await api.getTaskStatus(project.id, "images");
        if (!active) return;
        setTask(st);
        if (st.status === "running") {
          await onRefreshProject();
          setCacheBust(Date.now());
        }
      } catch {
        // ignore transient poll error
      }
    };
    poll();
    const timer = setInterval(() => {
      if (task.status === "running") {
        poll();
      }
    }, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [project.id, task.status, onRefreshProject]);

  useEffect(() => {
    if (task.warning) {
      setUpscaleWarning(task.warning);
    }
    if (task.status === "completed" || task.status === "cancelled") {
      onRefreshProject();
      setCacheBust(Date.now());
    } else if (task.status === "failed" && task.error) {
      onError(task.error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.status, task.warning]);

  const handleStopTask = async () => {
    onError("");
    try {
      const st = await api.stopTask(project.id, "images");
      setTask(st);
    } catch (err) {
      onError(err.message);
    }
  };

  const handleStartBatch = async ({ force = false, testOne = false } = {}) => {
    onError("");
    try {
      const st = await api.startImagesBatch(project.id, {
        force_regenerate: force,
        provider,
        test_one: testOne,
      });
      setTask(st);
    } catch (err) {
      onError(err.message);
    }
  };

  const handleGeneratePlaceholders = async () => {
    setGeneratingPlaceholders(true);
    onError("");
    try {
      await api.generatePlaceholderImages(project.id);
      await onRefreshProject();
      setCacheBust(Date.now());
    } catch (err) {
      onError(err.message);
    } finally {
      setGeneratingPlaceholders(false);
    }
  };

  const handleSaveAndRegenImage = async (scene, newSeed = false) => {
    setRegenIdx(scene.scene_index);
    onError("");
    try {
      const updatedPrompt = editingPrompt[scene.scene_index];
      if (updatedPrompt !== undefined && updatedPrompt !== scene.image_prompt) {
        await api.updateScene(project.id, scene.scene_index, {
          image_prompt: updatedPrompt,
        });
      }
      const res = await api.regenerateSceneImage(project.id, scene.scene_index, {
        provider,
        new_seed: newSeed,
      });
      if (res?.upscale_warning) {
        setUpscaleWarning(res.upscale_warning);
      }
      await onRefreshProject();
      setCacheBust(Date.now());
    } catch (err) {
      onError(err.message);
    } finally {
      setRegenIdx(null);
    }
  };

  const handleUploadSceneImage = async (sceneIndex, file) => {
    if (!file) return;
    setRegenIdx(sceneIndex);
    onError("");
    try {
      await api.uploadSceneImage(project.id, sceneIndex, file);
      await onRefreshProject();
      setCacheBust(Date.now());
    } catch (err) {
      onError(err.message);
    } finally {
      setRegenIdx(null);
    }
  };

  const etaText = formatEta(task.eta_seconds);

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
            Step 6 of 8
          </span>
          <h2 className="mt-1 text-2xl font-bold text-white">
            Scene Illustrations ({completedCount}/{scenes.length})
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            1920×1080 anime watercolor art generated sequentially via FastSD CPU + Upscayl (or Gemini fallback).
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            disabled={task.status === "running"}
            className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-xs font-semibold text-slate-200 focus:border-indigo-500 focus:outline-none"
          >
            <option value="local_sd">Local SD (FastSD CPU + Upscayl)</option>
            <option value="gemini">Gemini Image API (Fallback)</option>
          </select>

          <button
            type="button"
            onClick={() => handleStartBatch({ force: false, testOne: true })}
            disabled={task.status === "running" || scenes.length === 0}
            className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-500/40 bg-indigo-500/10 px-3.5 py-2.5 text-xs font-bold text-indigo-200 transition hover:bg-indigo-500/20 disabled:opacity-50"
            title="Generate & upscale 1 scene first to verify quality before running all scenes"
          >
            <FlaskConical className="h-4 w-4 text-indigo-400" />
            Test One Image
          </button>

          <button
            type="button"
            onClick={() => handleStartBatch({ force: false, testOne: false })}
            disabled={task.status === "running" || allDone}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {task.status === "running" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {completedCount > 0 && !allDone
              ? `Generate Remaining (${scenes.length - completedCount})`
              : "Generate All Scene Images"}
          </button>

          {completedCount > 0 && (
            <button
              type="button"
              onClick={() => handleStartBatch({ force: true, testOne: false })}
              disabled={task.status === "running"}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:bg-slate-700 disabled:opacity-50"
            >
              <RefreshCw className="h-4 w-4" />
              Regenerate All
            </button>
          )}

          {!allDone && (
            <button
              type="button"
              onClick={handleGeneratePlaceholders}
              disabled={task.status === "running" || generatingPlaceholders}
              className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3.5 py-2.5 text-xs font-bold text-amber-300 transition hover:bg-amber-500/20 disabled:opacity-50"
              title="Instant offline pastel backdrops for testing video render"
            >
              {generatingPlaceholders ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Palette className="h-4 w-4" />
              )}
              Pastel Test Art
            </button>
          )}

          <button
            type="button"
            onClick={onProceedToRender}
            disabled={!allDone || task.status === "running"}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-500/20 transition hover:bg-emerald-500 disabled:opacity-40"
          >
            Next: Render Video
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Local Services Warning if FastSD/Upscayl not ready */}
      {provider === "local_sd" && localHealth && !localHealth.ok && (
        <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-amber-500/40 bg-amber-950/30 px-4 py-3 text-xs text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <div>
            <span className="font-bold">Local SD setup needed:</span>{" "}
            {localHealth.errors.join(" · ")} — Check <strong>Settings</strong> or switch to Gemini API fallback.
          </div>
        </div>
      )}

      {upscaleWarning && (
        <div className="mb-5 flex items-start justify-between gap-2.5 rounded-xl border border-amber-500/40 bg-amber-950/30 px-4 py-3 text-xs text-amber-200">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
            <div>
              <span className="font-bold">Upscaler Fallback Notice:</span> {upscaleWarning}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setUpscaleWarning("")}
            className="text-amber-300 underline hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Style Badge + Progress Bar + ETA */}
      <div className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-300">
          <div className="flex flex-wrap items-center gap-2">
            <Palette className="h-4 w-4 text-amber-400" />
            <span className="font-semibold text-amber-300">Locked Style:</span>
            <span>
              Hand-painted anime watercolor · Soft pastel · Lush green nature · Dreamy sky · Warm golden light (1920×1080)
            </span>
          </div>
          <span className="inline-flex items-center gap-1 rounded-md bg-indigo-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-300">
            <Cpu className="h-3.5 w-3.5" />
            {provider === "local_sd" ? "FastSD CPU + Upscayl" : "Gemini Image API"}
          </span>
        </div>

        {task.status === "running" && (
          <div className="mt-4">
            <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="font-medium text-indigo-300">{task.message}</span>
              <div className="flex items-center gap-3">
                {etaText && (
                  <span className="inline-flex items-center gap-1 text-amber-300">
                    <Clock className="h-3.5 w-3.5" />
                    {etaText}
                  </span>
                )}
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
            <div className="h-3 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-amber-400 transition-all duration-300"
                style={{ width: `${task.progress}%` }}
              />
            </div>
          </div>
        )}

        {task.status === "cancelled" && (
          <div className="mt-4 rounded-xl border border-amber-500/40 bg-amber-950/30 px-4 py-2.5 text-xs text-amber-200">
            {task.message || "Image generation stopped. Completed scenes are kept — click Generate Remaining anytime to resume."}
          </div>
        )}
      </div>

      {/* Image Grid */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {scenes.map((sc) => {
          const promptVal =
            editingPrompt[sc.scene_index] !== undefined
              ? editingPrompt[sc.scene_index]
              : sc.image_prompt;
          const isRegen = regenIdx === sc.scene_index;
          const liveStatus =
            task.status === "running"
              ? task.scene_statuses?.[String(sc.scene_index)] || (sc.image_url ? "done" : "queued")
              : sc.image_url
              ? "done"
              : task.scene_statuses?.[String(sc.scene_index)] || "queued";

          return (
            <div
              key={sc.scene_index}
              className="flex flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70"
            >
              <div className="relative aspect-video bg-slate-950">
                {sc.image_url ? (
                  <img
                    src={`${sc.image_url}?t=${cacheBust}`}
                    alt={`Scene ${sc.scene_index}`}
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center text-slate-600">
                    {liveStatus === "generating" || liveStatus === "upscaling" ? (
                      <Loader2 className="mb-1.5 h-8 w-8 animate-spin text-indigo-400" />
                    ) : (
                      <ImageIcon className="mb-1.5 h-8 w-8" />
                    )}
                    <span className="text-xs capitalize">{liveStatus}</span>
                  </div>
                )}

                <span className="absolute left-2.5 top-2.5 rounded-md bg-slate-950/85 px-2 py-0.5 text-xs font-bold text-white backdrop-blur">
                  Scene {sc.scene_index}
                </span>

                <span
                  className={`absolute right-2.5 top-2.5 rounded-md px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide backdrop-blur ${
                    STATUS_BADGE[liveStatus] || STATUS_BADGE.queued
                  }`}
                >
                  {liveStatus}
                </span>
              </div>

              <div className="flex flex-1 flex-col justify-between p-4">
                <div>
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <p className="line-clamp-2 flex-1 text-xs text-slate-300">
                      {sc.narration}
                    </p>
                    {sc.image_seed && (
                      <span className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                        #{sc.image_seed}
                      </span>
                    )}
                  </div>
                  <textarea
                    rows={2}
                    value={promptVal}
                    onChange={(e) =>
                      setEditingPrompt((prev) => ({
                        ...prev,
                        [sc.scene_index]: e.target.value,
                      }))
                    }
                    className="w-full rounded-lg border border-slate-800 bg-slate-950 p-2 text-[11px] leading-relaxed text-slate-300 focus:border-indigo-500 focus:outline-none"
                  />
                </div>

                <div className="mt-3 flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleSaveAndRegenImage(sc, false)}
                    disabled={isRegen || task.status === "running"}
                    className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs font-semibold text-slate-200 transition hover:border-indigo-500 hover:text-white disabled:opacity-50"
                    title="Regenerate using character-group seed"
                  >
                    {isRegen ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
                        Painting...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="h-3.5 w-3.5 text-indigo-400" />
                        Regenerate
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={() => handleSaveAndRegenImage(sc, true)}
                    disabled={isRegen || task.status === "running"}
                    className="inline-flex items-center justify-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs font-semibold text-amber-300 transition hover:border-amber-400 hover:text-amber-200 disabled:opacity-50"
                    title="Regenerate with a brand new random seed"
                  >
                    <Dices className="h-3.5 w-3.5" />
                    New Seed
                  </button>

                  <label
                    className="inline-flex cursor-pointer items-center justify-center rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs font-semibold text-slate-300 transition hover:border-emerald-500 hover:text-white"
                    title="Upload a custom image file"
                  >
                    <Upload className="h-3.5 w-3.5 text-emerald-400" />
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) handleUploadSceneImage(sc.scene_index, f);
                        e.target.value = "";
                      }}
                      className="hidden"
                    />
                  </label>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
