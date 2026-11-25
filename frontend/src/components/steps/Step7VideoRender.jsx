import React, { useEffect, useState } from "react";
import {
  ArrowRight,
  Captions,
  Download,
  Film,
  Loader2,
  Music,
  Square,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { api } from "../../api/client";

export default function Step7VideoRender({
  project,
  onRefreshProject,
  onError,
  onProceedToYouTube,
}) {
  const [bgmVolume, setBgmVolume] = useState(project?.bgm_volume ?? 0.18);
  const [autoDuck, setAutoDuck] = useState(project?.auto_duck ?? true);
  const [burnSubtitles, setBurnSubtitles] = useState(project?.burn_subtitles ?? true);
  const [uploadingBgm, setUploadingBgm] = useState(false);
  const [task, setTask] = useState({ status: "idle", progress: 0, message: "" });
  const [cacheBust, setCacheBust] = useState(Date.now());

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const st = await api.getTaskStatus(project.id, "render");
        if (!active) return;
        setTask(st);
      } catch {
        // ignore transient error
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
  }, [project.id, task.status]);

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
      const st = await api.stopTask(project.id, "render");
      setTask(st);
    } catch (err) {
      onError(err.message);
    }
  };

  const handleBgmUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingBgm(true);
    onError("");
    try {
      await api.uploadBgm(project.id, file);
      await onRefreshProject();
    } catch (err) {
      onError(err.message);
    } finally {
      setUploadingBgm(false);
      e.target.value = "";
    }
  };

  const handleRemoveBgm = async () => {
    onError("");
    try {
      await api.deleteBgm(project.id);
      await onRefreshProject();
    } catch (err) {
      onError(err.message);
    }
  };

  const handleStartRender = async (testPreview15s = false) => {
    onError("");
    try {
      const st = await api.startRender(project.id, {
        bgm_volume: Number(bgmVolume),
        auto_duck: autoDuck,
        burn_subtitles: burnSubtitles,
        test_preview_15s: testPreview15s,
      });
      setTask(st);
    } catch (err) {
      onError(err.message);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
            Step 7 of 8
          </span>
          <h2 className="mt-1 text-2xl font-bold text-white">Render Full 1080p Video</h2>
          <p className="mt-1 text-sm text-slate-400">
            Ken Burns zoom/pan, crossfade transitions, auto-ducked background music, and burned-in subtitles at 1920×1080 24fps.
          </p>
        </div>

        <button
          type="button"
          onClick={onProceedToYouTube}
          disabled={!project?.video_url || task.status === "running"}
          className="inline-flex items-center gap-2 self-start rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500 disabled:opacity-40"
        >
          Next: YouTube Package
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-12">
        {/* Render Settings */}
        <div className="space-y-5 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 lg:col-span-5">
          <h3 className="text-base font-bold text-white">Render Options</h3>

          {/* BGM Upload */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                <Music className="h-4 w-4 text-indigo-400" />
                Background Music <span className="text-xs text-slate-500">(optional)</span>
              </span>
              {project?.bgm_url && (
                <button
                  type="button"
                  onClick={handleRemoveBgm}
                  className="inline-flex items-center gap-1 text-xs text-rose-400 hover:text-rose-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Remove
                </button>
              )}
            </div>

            {project?.bgm_url ? (
              <div className="space-y-3">
                <audio controls src={project.bgm_url} className="h-9 w-full" />
                <div>
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Music Volume</span>
                    <span>{Math.round(bgmVolume * 100)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0.05"
                    max="0.60"
                    step="0.02"
                    value={bgmVolume}
                    onChange={(e) => setBgmVolume(Number(e.target.value))}
                    className="mt-1.5 h-1.5 w-full cursor-pointer accent-indigo-500"
                  />
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-300">
                  <input
                    type="checkbox"
                    checked={autoDuck}
                    onChange={(e) => setAutoDuck(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-900 text-indigo-500"
                  />
                  Auto-duck music volume whenever narrator speaks
                </label>
              </div>
            ) : (
              <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-slate-700 px-3 py-4 text-xs font-medium text-slate-300 transition hover:border-indigo-500 hover:text-white">
                {uploadingBgm ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4 text-indigo-400" />
                )}
                Upload MP3 / WAV / M4A track
                <input
                  type="file"
                  accept=".mp3,.wav,.m4a,.ogg,.aac"
                  onChange={handleBgmUpload}
                  className="hidden"
                />
              </label>
            )}
          </div>

          {/* Subtitles */}
          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-4">
            <input
              type="checkbox"
              checked={burnSubtitles}
              onChange={(e) => setBurnSubtitles(e.target.checked)}
              className="mt-0.5 rounded border-slate-700 bg-slate-900 text-indigo-500"
            />
            <div>
              <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-200">
                <Captions className="h-4 w-4 text-indigo-400" />
                Burn-in Subtitles
              </div>
              <p className="mt-0.5 text-xs text-slate-400">
                {project?.language === "hindi"
                  ? "Uses Noto Sans Devanagari for crisp Hindi subtitles."
                  : "Clean high-contrast sans-serif subtitles timed to each scene."}
              </p>
            </div>
          </label>

          {/* Export Specs */}
          <div className="rounded-xl bg-slate-950/60 px-4 py-3 text-xs text-slate-400">
            <div className="flex justify-between py-0.5">
              <span>Resolution</span>
              <span className="font-semibold text-slate-200">1920 × 1080 (Full HD)</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span>Frame Rate</span>
              <span className="font-semibold text-slate-200">24 fps · H.264 MP4</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span>Motion & Transitions</span>
              <span className="font-semibold text-slate-200">Ken Burns + 0.4s Crossfade</span>
            </div>
          </div>

          <div className="space-y-2.5">
            <button
              type="button"
              onClick={() => handleStartRender(false)}
              disabled={task.status === "running"}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {task.status === "running" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Rendering Video...
                </>
              ) : (
                <>
                  <Film className="h-4 w-4" />
                  {project?.video_url ? "Re-Render Full Video" : "Start Full Video Render"}
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => handleStartRender(true)}
              disabled={task.status === "running"}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 text-xs font-bold text-amber-300 transition hover:bg-amber-500/20 disabled:opacity-50"
            >
              <Zap className="h-4 w-4" />
              Render 15s Test Preview (Fast Check)
            </button>
          </div>
        </div>

        {/* Video Preview & Progress */}
        <div className="flex flex-col justify-between rounded-2xl border border-slate-800 bg-slate-900/70 p-6 lg:col-span-7">
          <div>
            <h3 className="mb-3 text-base font-bold text-white">Video Output Preview</h3>

            {task.status === "running" && (
              <div className="mb-4 rounded-xl border border-indigo-500/30 bg-indigo-950/30 p-4">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="font-medium text-indigo-200">{task.message}</span>
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-white">{task.progress}%</span>
                    <button
                      type="button"
                      onClick={handleStopTask}
                      disabled={task.cancel_requested}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/50 bg-rose-500/15 px-3 py-1 text-xs font-bold text-rose-200 transition hover:bg-rose-500/25 disabled:opacity-50"
                    >
                      <Square className="h-3.5 w-3.5 fill-current" />
                      {task.cancel_requested ? "Stopping..." : "Stop Render"}
                    </button>
                  </div>
                </div>
                <div className="h-3 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-emerald-400 transition-all duration-300"
                    style={{ width: `${task.progress}%` }}
                  />
                </div>
              </div>
            )}

            {task.status === "cancelled" && (
              <div className="mb-4 rounded-xl border border-amber-500/40 bg-amber-950/30 px-4 py-2.5 text-xs text-amber-200">
                {task.message || "Video render stopped by user."}
              </div>
            )}

            {(project?.video_url || project?.preview_video_url) ? (
              <div className="space-y-4">
                {project?.video_url && (
                  <div className="space-y-2">
                    <video
                      controls
                      src={`${project.video_url}?t=${cacheBust}`}
                      className="aspect-video w-full rounded-xl border border-slate-800 bg-black"
                    />
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span className="text-xs text-emerald-400">
                        ✓ Full MP4 saved to disk and ready for download.
                      </span>
                      <a
                        href={api.downloadUrl(project.id, "video")}
                        className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-white transition hover:bg-slate-700"
                      >
                        <Download className="h-4 w-4 text-emerald-400" />
                        Download MP4
                      </a>
                    </div>
                  </div>
                )}

                {project?.preview_video_url && (
                  <div className="space-y-2 rounded-xl border border-amber-500/30 bg-amber-950/15 p-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-amber-300">
                        ⚡ 15-Second Test Preview
                      </span>
                      <a
                        href={project.preview_video_url}
                        download={`preview_15s_${project.id}.mp4`}
                        className="font-semibold text-amber-200 underline hover:text-white"
                      >
                        Download 15s Clip
                      </a>
                    </div>
                    <video
                      controls
                      src={`${project.preview_video_url}?t=${cacheBust}`}
                      className="aspect-video w-full rounded-lg border border-slate-800 bg-black"
                    />
                  </div>
                )}
              </div>
            ) : (
              <div className="flex aspect-video flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-950/60 text-center text-slate-500">
                <Film className="mb-2 h-10 w-10 text-slate-600" />
                <p className="text-sm font-medium text-slate-400">No rendered video yet</p>
                <p className="mt-1 max-w-sm text-xs">
                  Click &ldquo;Start Video Render&rdquo; to combine all scenes, voiceovers, Ken Burns motion, and subtitles.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
