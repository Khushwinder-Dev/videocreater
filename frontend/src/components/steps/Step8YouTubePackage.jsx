import React, { useState } from "react";
import {
  Check,
  Copy,
  Download,
  FileText,
  Film,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { api } from "../../api/client";

function CopyButton({ text, label = "Copy" }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1 text-xs font-medium text-slate-300 transition hover:border-indigo-500 hover:text-white"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : label}
    </button>
  );
}

export default function Step8YouTubePackage({
  project,
  onRefreshProject,
  onError,
}) {
  const [generating, setGenerating] = useState(false);
  const [regenThumbIdx, setRegenThumbIdx] = useState(null);
  const [thumbEdits, setThumbEdits] = useState({});
  const [cacheBust, setCacheBust] = useState(Date.now());

  const yt = project?.youtube_package || {};
  const hasPackage = Array.isArray(yt.titles) && yt.titles.length > 0;
  const scenes = project?.scenes || [];

  const handleGenerate = async () => {
    setGenerating(true);
    onError("");
    try {
      await api.generateYouTubePackage(project.id);
      await onRefreshProject();
      setCacheBust(Date.now());
    } catch (err) {
      onError(err.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleRegenThumbnail = async (idx, concept) => {
    setRegenThumbIdx(idx);
    onError("");
    try {
      const edit = thumbEdits[idx] || {};
      await api.regenerateThumbnail(project.id, {
        concept_index: idx,
        overlay_text: edit.overlay_text ?? concept.overlay_text,
        visual_description: edit.visual_description ?? concept.visual_description,
        source_scene_index: edit.source_scene_index ? Number(edit.source_scene_index) : null,
        use_fresh_ai_bg: !edit.source_scene_index,
      });
      await onRefreshProject();
      setCacheBust(Date.now());
    } catch (err) {
      onError(err.message);
    } finally {
      setRegenThumbIdx(null);
    }
  };

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
            Step 8 of 8
          </span>
          <h2 className="mt-1 text-2xl font-bold text-white">YouTube Publishing Package</h2>
          <p className="mt-1 text-sm text-slate-400">
            5 click-worthy titles (&lt;70 chars), timestamped SEO description, 15 tags, hashtags, and 3 rendered 1280×720 thumbnails.
          </p>
        </div>

        <button
          type="button"
          onClick={handleGenerate}
          disabled={generating}
          className="inline-flex items-center gap-2 self-start rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500 disabled:opacity-50"
        >
          {generating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Generating Package & Thumbnails...
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" />
              {hasPackage ? "Regenerate YouTube Package" : "Generate YouTube Package"}
            </>
          )}
        </button>
      </div>

      {/* Downloads Bar */}
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
        <span className="mr-2 text-xs font-bold uppercase tracking-wider text-slate-400">
          Downloads:
        </span>
        {project?.video_url && (
          <a
            href={api.downloadUrl(project.id, "video")}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white transition hover:bg-emerald-500"
          >
            <Film className="h-4 w-4" />
            Download Video (.mp4)
          </a>
        )}
        {hasPackage && (
          <a
            href={api.downloadUrl(project.id, "metadata")}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-white transition hover:bg-slate-700"
          >
            <FileText className="h-4 w-4 text-indigo-400" />
            Download Metadata (.txt)
          </a>
        )}
        {(yt.thumbnail_concepts || []).map((c, i) =>
          c.image_url ? (
            <a
              key={i}
              href={api.downloadUrl(project.id, `thumbnail_${i + 1}`)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 transition hover:bg-slate-700"
            >
              <Download className="h-3.5 w-3.5 text-amber-400" />
              Thumbnail {i + 1} (.png)
            </a>
          ) : null
        )}
      </div>

      {!hasPackage ? (
        <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 px-6 py-16 text-center">
          <Sparkles className="mx-auto mb-3 h-10 w-10 text-indigo-400" />
          <h3 className="text-lg font-bold text-white">Ready to build your YouTube Launch Kit</h3>
          <p className="mx-auto mt-1 max-w-lg text-sm text-slate-400">
            Click &ldquo;Generate YouTube Package&rdquo; to create 5 titles under 70 characters,
            chapter timestamps from your exact voiceover lengths, 15 SEO tags, and 3 bold 1280×720 thumbnails.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* 3 Thumbnails */}
          <div>
            <h3 className="mb-3 text-base font-bold text-white">
              3 Rendered Thumbnails (1280×720)
            </h3>
            <div className="grid gap-5 lg:grid-cols-3">
              {(yt.thumbnail_concepts || []).map((concept, idx) => {
                const edit = thumbEdits[idx] || {};
                const overlayVal = edit.overlay_text ?? concept.overlay_text;
                const isRegen = regenThumbIdx === idx;

                return (
                  <div
                    key={idx}
                    className="flex flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70"
                  >
                    <div className="relative aspect-video bg-slate-950">
                      {concept.image_url ? (
                        <img
                          src={`${concept.image_url}?t=${cacheBust}`}
                          alt={concept.concept_title}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full items-center justify-center text-slate-600">
                          <ImageIcon className="h-8 w-8" />
                        </div>
                      )}
                    </div>

                    <div className="flex flex-1 flex-col justify-between space-y-3 p-4">
                      <div>
                        <div className="text-xs font-bold text-indigo-300">
                          Concept #{idx + 1}: {concept.concept_title}
                        </div>
                        <label className="mt-2 block text-[11px] font-medium text-slate-400">
                          Bold Overlay Text
                        </label>
                        <input
                          type="text"
                          value={overlayVal}
                          onChange={(e) =>
                            setThumbEdits((prev) => ({
                              ...prev,
                              [idx]: { ...prev[idx], overlay_text: e.target.value },
                            }))
                          }
                          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm font-semibold text-white focus:border-indigo-500 focus:outline-none"
                        />

                        <label className="mt-2.5 block text-[11px] font-medium text-slate-400">
                          Background Source
                        </label>
                        <select
                          value={edit.source_scene_index || ""}
                          onChange={(e) =>
                            setThumbEdits((prev) => ({
                              ...prev,
                              [idx]: { ...prev[idx], source_scene_index: e.target.value },
                            }))
                          }
                          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                        >
                          <option value="">Fresh AI Thumbnail Background</option>
                          {scenes
                            .filter((s) => s.image_url)
                            .map((s) => (
                              <option key={s.scene_index} value={s.scene_index}>
                                Use Scene {s.scene_index} Image
                              </option>
                            ))}
                        </select>
                      </div>

                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => handleRegenThumbnail(idx, concept)}
                          disabled={isRegen}
                          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-indigo-500 hover:text-white disabled:opacity-50"
                        >
                          {isRegen ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <RefreshCw className="h-3.5 w-3.5 text-indigo-400" />
                          )}
                          Update Thumbnail
                        </button>
                        <a
                          href={api.downloadUrl(project.id, `thumbnail_${idx + 1}`)}
                          className="inline-flex items-center justify-center rounded-lg bg-slate-800 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-700"
                          title="Download PNG"
                        >
                          <Download className="h-3.5 w-3.5" />
                        </a>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 5 Titles */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <h3 className="mb-3 text-base font-bold text-white">5 Title Options (Under 70 Chars)</h3>
            <div className="space-y-2.5">
              {yt.titles.map((title, idx) => (
                <div
                  key={idx}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-2.5"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-bold text-indigo-400">#{idx + 1}</span>
                    <span className="text-sm font-medium text-white">{title}</span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`text-xs font-medium ${
                        title.length <= 70 ? "text-emerald-400" : "text-amber-400"
                      }`}
                    >
                      {title.length}/70 chars
                    </span>
                    <CopyButton text={title} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Description + Tags */}
          <div className="grid gap-6 lg:grid-cols-12">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 lg:col-span-7">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-base font-bold text-white">SEO Description & Timestamps</h3>
                <CopyButton text={yt.description || ""} />
              </div>
              <pre className="whitespace-pre-wrap rounded-xl border border-slate-800 bg-slate-950/70 p-4 font-sans text-xs leading-relaxed text-slate-200">
                {yt.description}
              </pre>
            </div>

            <div className="space-y-5 lg:col-span-5">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-base font-bold text-white">15 SEO Tags</h3>
                  <CopyButton text={(yt.tags || []).join(", ")} />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(yt.tags || []).map((tag, i) => (
                    <span
                      key={i}
                      className="rounded-md border border-slate-800 bg-slate-950 px-2.5 py-1 text-xs text-slate-300"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-base font-bold text-white">Hashtags</h3>
                  <CopyButton text={(yt.hashtags || []).join(" ")} />
                </div>
                <p className="rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-sm font-medium text-indigo-300">
                  {(yt.hashtags || []).join(" ")}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
