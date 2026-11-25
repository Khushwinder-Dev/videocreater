import React, { useEffect, useState } from "react";
import { ArrowRight, BookUser, Loader2, RefreshCw, Save, Wand2 } from "lucide-react";

export default function Step4Scenes({
  project,
  onGenerateScenes,
  onSaveAllScenes,
  onRegenerateSingleScene,
  onProceedToVoiceover,
}) {
  const [characterBible, setCharacterBible] = useState(project?.character_bible || "");
  const [scenes, setScenes] = useState(project?.scenes || []);
  const [generatingAll, setGeneratingAll] = useState(false);
  const [savingAll, setSavingAll] = useState(false);
  const [regenIdx, setRegenIdx] = useState(null);
  const [savedMsg, setSavedMsg] = useState("");

  useEffect(() => {
    setCharacterBible(project?.character_bible || "");
    setScenes(project?.scenes || []);
  }, [project?.character_bible, project?.scenes]);

  useEffect(() => {
    if (project && (!project.scenes || project.scenes.length === 0) && !generatingAll) {
      handleGenerateAll();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);

  const handleGenerateAll = async () => {
    setGeneratingAll(true);
    try {
      await onGenerateScenes();
    } finally {
      setGeneratingAll(false);
    }
  };

  const handleSceneChange = (idx, field, value) => {
    setScenes((prev) =>
      prev.map((s) => (s.scene_index === idx ? { ...s, [field]: value } : s))
    );
  };

  const handleSaveAll = async () => {
    setSavingAll(true);
    setSavedMsg("");
    try {
      await onSaveAllScenes({
        character_bible: characterBible,
        scenes: scenes.map((s) => ({
          scene_index: s.scene_index,
          narration: s.narration,
          image_prompt: s.image_prompt,
        })),
      });
      setSavedMsg("All scenes saved!");
      setTimeout(() => setSavedMsg(""), 2500);
    } finally {
      setSavingAll(false);
    }
  };

  const handleRegenOne = async (sceneIndex) => {
    setRegenIdx(sceneIndex);
    try {
      // Save edits first so context is fresh
      await onSaveAllScenes({
        character_bible: characterBible,
        scenes: scenes.map((s) => ({
          scene_index: s.scene_index,
          narration: s.narration,
          image_prompt: s.image_prompt,
        })),
      });
      await onRegenerateSingleScene(sceneIndex);
    } finally {
      setRegenIdx(null);
    }
  };

  const handleNext = async () => {
    setSavingAll(true);
    try {
      await onSaveAllScenes({
        character_bible: characterBible,
        scenes: scenes.map((s) => ({
          scene_index: s.scene_index,
          narration: s.narration,
          image_prompt: s.image_prompt,
        })),
      });
      await onProceedToVoiceover();
    } finally {
      setSavingAll(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
            Step 4 of 8
          </span>
          <h2 className="mt-1 text-2xl font-bold text-white">
            Storyboard Scenes ({scenes.length})
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            {project?.target_duration_sec <= 30
              ? "15-second Test Mode: 2–3 quick scenes with a shared Character Bible."
              : "Script split into ~8–10 sec scenes with a shared Character Bible for visual consistency."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={handleGenerateAll}
            disabled={generatingAll || savingAll}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-indigo-500 hover:text-white disabled:opacity-50"
          >
            {generatingAll ? (
              <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
            ) : (
              <RefreshCw className="h-4 w-4 text-indigo-400" />
            )}
            {generatingAll ? "Splitting Script..." : "Regenerate All Scenes"}
          </button>

          <button
            type="button"
            onClick={handleSaveAll}
            disabled={savingAll || generatingAll || scenes.length === 0}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {savedMsg || "Save All Edits"}
          </button>

          <button
            type="button"
            onClick={handleNext}
            disabled={savingAll || generatingAll || scenes.length === 0}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500 disabled:opacity-50"
          >
            Next: Voiceover
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Character Bible Card */}
      <div className="mb-6 rounded-2xl border border-indigo-500/30 bg-indigo-950/20 p-5">
        <label className="mb-2 flex items-center gap-2 text-sm font-bold text-indigo-300">
          <BookUser className="h-4 w-4" />
          Character Bible (automatically injected into every scene image prompt)
        </label>
        <textarea
          value={characterBible}
          onChange={(e) => setCharacterBible(e.target.value)}
          rows={3}
          placeholder="Consistent visual descriptions of every recurring character..."
          className="w-full rounded-xl border border-slate-800 bg-slate-950/90 p-3.5 text-xs leading-relaxed text-slate-200 focus:border-indigo-500 focus:outline-none"
        />
      </div>

      {generatingAll && scenes.length === 0 ? (
        <div className="flex h-80 flex-col items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/50 text-slate-300">
          <Loader2 className="mb-3 h-8 w-8 animate-spin text-indigo-400" />
          <p className="text-sm font-medium">
            Breaking script into 60–75 scenes and building the Character Bible...
          </p>
          <p className="mt-1 text-xs text-slate-500">Please wait 15–30 seconds.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {scenes.map((scene) => (
            <div
              key={scene.scene_index}
              className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-slate-700"
            >
              <div className="mb-3 flex items-center justify-between">
                <span className="rounded-lg bg-slate-800 px-2.5 py-1 text-xs font-bold text-indigo-300">
                  Scene {scene.scene_index}
                </span>
                <button
                  type="button"
                  onClick={() => handleRegenOne(scene.scene_index)}
                  disabled={regenIdx === scene.scene_index || generatingAll}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1 text-xs font-medium text-slate-300 transition hover:border-indigo-500 hover:text-white disabled:opacity-50"
                >
                  {regenIdx === scene.scene_index ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Wand2 className="h-3.5 w-3.5 text-indigo-400" />
                  )}
                  Regenerate Scene
                </button>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-400">
                    Voiceover Narration
                  </label>
                  <textarea
                    rows={3}
                    value={scene.narration}
                    onChange={(e) =>
                      handleSceneChange(scene.scene_index, "narration", e.target.value)
                    }
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 p-3 text-sm leading-relaxed text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-400">
                    Image Prompt (Anime Watercolor 16:9)
                  </label>
                  <textarea
                    rows={3}
                    value={scene.image_prompt}
                    onChange={(e) =>
                      handleSceneChange(scene.scene_index, "image_prompt", e.target.value)
                    }
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs leading-relaxed text-slate-300 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
