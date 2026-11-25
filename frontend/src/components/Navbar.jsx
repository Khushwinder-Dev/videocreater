import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Film,
  FolderKanban,
  Plus,
  Settings,
} from "lucide-react";

export default function Navbar({
  health,
  activeView,
  onGoProjects,
  onGoSettings,
  onNewProject,
  activeProject,
}) {
  const localOk = health?.local_services?.fastsd_ok;
  const isLocal = health?.image_provider === "local_sd";

  return (
    <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <button
            onClick={onGoProjects}
            className="flex items-center gap-2.5 text-left transition hover:opacity-90"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-indigo-500/25">
              <Film className="h-5 w-5 text-white" />
            </div>
            <div>
              <span className="block text-base font-bold tracking-tight text-white">
                StoryTube Studio
              </span>
              <span className="block text-[11px] text-slate-400">
                AI Story Video Automation
              </span>
            </div>
          </button>

          {activeView === "wizard" && activeProject && (
            <div className="hidden items-center gap-2 border-l border-slate-800 pl-4 md:flex">
              <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-300">
                {activeProject.language === "hindi" ? "Hindi" : "English"}
              </span>
              <span className="max-w-[220px] truncate text-sm font-medium text-slate-200">
                {activeProject.title}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2.5">
          {health && (
            <div className="hidden items-center gap-2 text-xs xl:flex">
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium ${
                  health.gemini_configured
                    ? "bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/25"
                    : "bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/30"
                }`}
              >
                {health.gemini_configured ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  <AlertTriangle className="h-3.5 w-3.5" />
                )}
                {health.gemini_configured ? "Gemini Ready" : "Missing API Key"}
              </span>

              {isLocal && (
                <button
                  type="button"
                  onClick={onGoSettings}
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium transition ${
                    localOk
                      ? "bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/25"
                      : "bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/30 hover:bg-amber-500/20"
                  }`}
                >
                  <Cpu className="h-3.5 w-3.5" />
                  {localOk ? "FastSD Ready" : "FastSD Offline"}
                </button>
              )}

              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium ${
                  health.ffmpeg_installed
                    ? "bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/25"
                    : "bg-rose-500/10 text-rose-300 ring-1 ring-rose-500/30"
                }`}
              >
                {health.ffmpeg_installed ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  <AlertTriangle className="h-3.5 w-3.5" />
                )}
                {health.ffmpeg_installed ? "FFmpeg Ready" : "FFmpeg Missing"}
              </span>
            </div>
          )}

          <button
            onClick={onGoProjects}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              activeView === "projects"
                ? "bg-slate-800 text-white"
                : "text-slate-300 hover:bg-slate-800/70 hover:text-white"
            }`}
          >
            <FolderKanban className="h-4 w-4" />
            Projects
          </button>

          <button
            onClick={onGoSettings}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              activeView === "settings"
                ? "bg-slate-800 text-white"
                : "text-slate-300 hover:bg-slate-800/70 hover:text-white"
            }`}
          >
            <Settings className="h-4 w-4" />
            Settings
          </button>

          <button
            onClick={onNewProject}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-sm font-semibold text-white shadow-sm shadow-indigo-500/30 transition hover:bg-indigo-500"
          >
            <Plus className="h-4 w-4" />
            New Video
          </button>
        </div>
      </div>
    </header>
  );
}
