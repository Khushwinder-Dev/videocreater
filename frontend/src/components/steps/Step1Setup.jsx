import React, { useState } from "react";
import { ArrowRight, Clock, Globe2, Loader2, Sparkles, Zap } from "lucide-react";

const GENRES = [
  {
    id: "moral_stories",
    title: "Moral Stories",
    desc: "Heartwarming life lessons, karma, kindness, and emotional twists.",
  },
  {
    id: "kids",
    title: "Kids & Bedtime",
    desc: "Whimsical adventures, talking animals, gentle wonder, and cozy endings.",
  },
  {
    id: "mythology",
    title: "Mythology & Folklore",
    desc: "Timeless legends, ancient wisdom, courage, and sacred mysteries.",
  },
  {
    id: "mystery",
    title: "Mystery & Suspense",
    desc: "Atmospheric secrets, village folklore, clever clues, and startling reveals.",
  },
  {
    id: "horror",
    title: "Horror Stories",
    desc: "Eerie hauntings, spine-chilling folklore, shadows, and terrifying twists.",
  },
];

export default function Step1Setup({ project, onSaveAndContinue }) {
  const [title, setTitle] = useState(project?.title || "");
  const [language, setLanguage] = useState(project?.language || "english");
  const [genre, setGenre] = useState(project?.genre || "moral_stories");
  const [isTestMode, setIsTestMode] = useState(project?.target_duration_sec === 15);
  const [targetLength, setTargetLength] = useState(
    project?.target_length_min && project.target_length_min >= 2
      ? project.target_length_min
      : 10
  );
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSaveAndContinue({
        title: title.trim(),
        language,
        genre,
        target_length_min: isTestMode ? 0 : Number(targetLength),
        target_duration_sec: isTestMode ? 15 : Number(targetLength) * 60,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
      <div className="mb-6">
        <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
          Step 1 of 8
        </span>
        <h2 className="mt-1 text-2xl font-bold text-white">Configure Your Story Video</h2>
        <p className="mt-1 text-sm text-slate-400">
          Choose the narration language, story genre, and target video duration.
        </p>
      </div>

      <div className="space-y-6 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl">
        {/* Optional working title */}
        <div>
          <label className="block text-sm font-medium text-slate-200">
            Working Project Name <span className="text-slate-500">(optional)</span>
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g., The Banyan Tree Promise (auto-filled when you pick a topic)"
            className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        {/* Language */}
        <div>
          <label className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-200">
            <Globe2 className="h-4 w-4 text-indigo-400" />
            Narration & Subtitles Language
          </label>
          <div className="grid grid-cols-2 gap-3">
            {[
              { id: "english", label: "English", sub: "~1,400 words for 10 min" },
              { id: "hindi", label: "Hindi (हिन्दी)", sub: "~1,300 words · Devanagari subtitles" },
            ].map((lang) => (
              <button
                key={lang.id}
                type="button"
                onClick={() => setLanguage(lang.id)}
                className={`rounded-xl border p-4 text-left transition ${
                  language === lang.id
                    ? "border-indigo-500 bg-indigo-500/15 text-white ring-1 ring-indigo-500/40"
                    : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700"
                }`}
              >
                <div className="text-sm font-bold">{lang.label}</div>
                <div className="mt-0.5 text-xs text-slate-400">{lang.sub}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Genre */}
        <div>
          <label className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-200">
            <Sparkles className="h-4 w-4 text-indigo-400" />
            Story Genre
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            {GENRES.map((g) => (
              <button
                key={g.id}
                type="button"
                onClick={() => setGenre(g.id)}
                className={`rounded-xl border p-4 text-left transition ${
                  genre === g.id
                    ? "border-indigo-500 bg-indigo-500/15 text-white ring-1 ring-indigo-500/40"
                    : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700"
                }`}
              >
                <div className="text-sm font-bold">{g.title}</div>
                <div className="mt-1 text-xs leading-relaxed text-slate-400">{g.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Target Length + 15-Sec Quick Test */}
        <div>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-sm font-medium text-slate-200">
              <Clock className="h-4 w-4 text-indigo-400" />
              Target Video Length
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsTestMode((prev) => !prev)}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1 text-xs font-bold transition ${
                  isTestMode
                    ? "border-amber-400 bg-amber-500/20 text-amber-300 ring-1 ring-amber-400/40"
                    : "border-slate-700 bg-slate-950 text-slate-300 hover:border-amber-400/60 hover:text-amber-200"
                }`}
              >
                <Zap className="h-3.5 w-3.5" />
                {isTestMode ? "15s Quick Test ON" : "Enable 15s Quick Test"}
              </button>
              <span className="rounded-lg bg-indigo-500/20 px-3 py-1 text-sm font-bold text-indigo-300">
                {isTestMode ? "15 seconds (2–3 scenes)" : `${targetLength} minutes`}
              </span>
            </div>
          </div>

          {isTestMode ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 px-4 py-3 text-xs text-amber-200/90">
              <strong>Quick Test Mode active:</strong> Generates a crisp ~35-word micro-story, 2–3 scenes, fast voiceover &amp; art, and a 15-second 1080p MP4 so you can verify the entire pipeline in seconds.
            </div>
          ) : (
            <>
              <input
                type="range"
                min="3"
                max="20"
                step="1"
                value={targetLength}
                onChange={(e) => setTargetLength(Number(e.target.value))}
                className="mt-1 h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-800 accent-indigo-500"
              />
              <div className="mt-1.5 flex justify-between text-xs text-slate-500">
                <span>3 min (short)</span>
                <span>10 min (YouTube sweet spot)</span>
                <span>20 min (long)</span>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="mt-6 flex justify-end">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500 disabled:opacity-60"
        >
          {saving ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Saving Setup...
            </>
          ) : (
            <>
              Continue to Topic Suggestions
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </button>
      </div>
    </form>
  );
}
