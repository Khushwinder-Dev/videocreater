import React, { useEffect, useMemo, useState } from "react";
import { ArrowRight, BookOpen, Loader2, RefreshCw, Save } from "lucide-react";

export default function Step3Script({
  project,
  onGenerateScript,
  onSaveScript,
  onProceedToScenes,
}) {
  const [scriptText, setScriptText] = useState(project?.script || "");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedNotice, setSavedNotice] = useState("");

  useEffect(() => {
    setScriptText(project?.script || "");
  }, [project?.script]);

  useEffect(() => {
    if (project && !project.script && !generating) {
      handleGenerate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);

  const stats = useMemo(() => {
    const words = scriptText.trim() ? scriptText.trim().split(/\s+/).length : 0;
    const wpm = project?.language === "hindi" ? 130 : 140;
    const durSec = project?.target_duration_sec ?? (project?.target_length_min || 10) * 60;
    const isTest = durSec <= 30;
    const estSeconds = Math.round((words / wpm) * 60);
    const estLabel = isTest ? `~${estSeconds} sec` : `~${(words / wpm).toFixed(1)} min`;
    const targetWords = Math.max(25, Math.round(wpm * (durSec / 60)));
    return { words, estLabel, targetWords };
  }, [scriptText, project?.language, project?.target_length_min, project?.target_duration_sec]);

  const handleGenerate = async () => {
    setGenerating(true);
    setSavedNotice("");
    try {
      const updated = await onGenerateScript();
      if (updated?.script) setScriptText(updated.script);
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveOnly = async () => {
    setSaving(true);
    setSavedNotice("");
    try {
      await onSaveScript(scriptText);
      setSavedNotice("Saved to disk");
      setTimeout(() => setSavedNotice(""), 2500);
    } finally {
      setSaving(false);
    }
  };

  const handleNext = async () => {
    setSaving(true);
    try {
      await onSaveScript(scriptText);
      await onProceedToScenes();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
            Step 3 of 8
          </span>
          <h2 className="mt-1 text-2xl font-bold text-white">Review & Edit Story Script</h2>
          <p className="mt-1 text-sm text-slate-400">
            Topic: <span className="font-medium text-slate-200">{project?.selected_topic}</span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating || saving}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-indigo-500 hover:text-white disabled:opacity-50"
          >
            {generating ? (
              <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
            ) : (
              <RefreshCw className="h-4 w-4 text-indigo-400" />
            )}
            {generating ? "Writing Script..." : "Regenerate Script"}
          </button>

          <button
            type="button"
            onClick={handleSaveOnly}
            disabled={saving || generating || !scriptText.trim()}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {savedNotice || "Save Draft"}
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-xs">
        <div className="flex items-center gap-4 text-slate-300">
          <span className="inline-flex items-center gap-1.5">
            <BookOpen className="h-4 w-4 text-indigo-400" />
            <strong>{stats.words}</strong> words (target ~{stats.targetWords})
          </span>
          <span>
            Estimated narration: <strong className="text-emerald-400">{stats.estLabel}</strong>
          </span>
        </div>
        <span className="text-slate-400">
          Hook → 3-Act Arc → Emotional Ending → Moral
        </span>
      </div>

      {generating && !scriptText ? (
        <div className="flex h-96 flex-col items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/50 text-slate-300">
          <Loader2 className="mb-3 h-8 w-8 animate-spin text-indigo-400" />
          <p className="text-sm font-medium">Crafting your full voiceover script with Gemini...</p>
          <p className="mt-1 text-xs text-slate-500">This usually takes 10–20 seconds.</p>
        </div>
      ) : (
        <textarea
          value={scriptText}
          onChange={(e) => setScriptText(e.target.value)}
          rows={20}
          placeholder="Your full narration script will appear here..."
          className="w-full rounded-2xl border border-slate-800 bg-slate-900/80 p-5 text-sm leading-7 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      )}

      <div className="mt-6 flex justify-end">
        <button
          type="button"
          onClick={handleNext}
          disabled={!scriptText.trim() || generating || saving}
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500 disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Save & Split into Scenes
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
