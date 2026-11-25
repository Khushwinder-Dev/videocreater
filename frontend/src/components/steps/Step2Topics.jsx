import React, { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, Loader2, PenLine, RefreshCw, Sparkles } from "lucide-react";

export default function Step2Topics({
  project,
  onGenerateTopics,
  onSelectTopic,
}) {
  const [loading, setLoading] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [customTopic, setCustomTopic] = useState("");
  const [customHook, setCustomHook] = useState("");

  const topics = project?.topics || [];

  useEffect(() => {
    if (project && topics.length === 0 && !loading) {
      handleGenerate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      await onGenerateTopics();
    } finally {
      setLoading(false);
    }
  };

  const handlePick = async (title, hook) => {
    setSelecting(true);
    try {
      await onSelectTopic({ title, hook });
    } finally {
      setSelecting(false);
    }
  };

  const handleCustomSubmit = async (e) => {
    e.preventDefault();
    if (!customTopic.trim()) return;
    await handlePick(customTopic.trim(), customHook.trim());
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
            Step 2 of 8
          </span>
          <h2 className="mt-1 text-2xl font-bold text-white">Choose a Story Topic</h2>
          <p className="mt-1 text-sm text-slate-400">
            Select one of 10 trending, original story concepts from Gemini or write your own topic.
          </p>
        </div>

        <button
          type="button"
          onClick={handleGenerate}
          disabled={loading || selecting}
          className="inline-flex items-center gap-2 self-start rounded-xl border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-indigo-500 hover:text-white disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
          ) : (
            <RefreshCw className="h-4 w-4 text-indigo-400" />
          )}
          {loading ? "Generating 10 Topics..." : "Regenerate Topics"}
        </button>
      </div>

      {/* Custom Topic Box */}
      <form
        onSubmit={handleCustomSubmit}
        className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/70 p-5"
      >
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
          <PenLine className="h-4 w-4 text-amber-400" />
          Or Enter Your Own Custom Topic
        </div>
        <div className="grid gap-3 sm:grid-cols-12">
          <input
            type="text"
            value={customTopic}
            onChange={(e) => setCustomTopic(e.target.value)}
            placeholder="Custom story title or idea..."
            className="sm:col-span-5 rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />
          <input
            type="text"
            value={customHook}
            onChange={(e) => setCustomHook(e.target.value)}
            placeholder="Optional 1-line opening hook..."
            className="sm:col-span-5 rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!customTopic.trim() || selecting}
            className="sm:col-span-2 inline-flex items-center justify-center gap-1.5 rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-bold text-slate-950 transition hover:bg-amber-400 disabled:opacity-40"
          >
            Use Topic
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </form>

      {/* AI Generated 10 Topics */}
      {loading && topics.length === 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div
              key={idx}
              className="h-28 animate-pulse rounded-2xl border border-slate-800 bg-slate-900/60"
            />
          ))}
        </div>
      ) : (
        <div className="grid gap-3.5 sm:grid-cols-2">
          {topics.map((item, idx) => {
            const isSelected = project?.selected_topic === item.title;
            return (
              <button
                key={idx}
                type="button"
                disabled={selecting || loading}
                onClick={() => handlePick(item.title, item.hook)}
                className={`group flex flex-col justify-between rounded-2xl border p-4 text-left transition ${
                  isSelected
                    ? "border-indigo-500 bg-indigo-500/15 ring-1 ring-indigo-500/50"
                    : "border-slate-800 bg-slate-900/70 hover:border-indigo-500/60 hover:bg-slate-900"
                }`}
              >
                <div>
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-400">
                      <Sparkles className="h-3.5 w-3.5" />
                      Topic #{idx + 1}
                    </span>
                    {isSelected && (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Selected
                      </span>
                    )}
                  </div>
                  <h3 className="text-base font-bold text-white group-hover:text-indigo-200">
                    {item.title}
                  </h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{item.hook}</p>
                </div>

                <div className="mt-3 flex items-center justify-end text-xs font-semibold text-indigo-400 opacity-80 group-hover:opacity-100">
                  Select & Write Script →
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
