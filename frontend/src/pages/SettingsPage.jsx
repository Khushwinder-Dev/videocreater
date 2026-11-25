import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Loader2,
  RefreshCw,
  Save,
  Settings as SettingsIcon,
  Sparkles,
} from "lucide-react";
import { api } from "../api/client";
import ErrorBanner from "../components/ErrorBanner";

export default function SettingsPage({ onSettingsSaved }) {
  const [form, setForm] = useState({
    image_provider: "local_sd",
    fastsd_url: "http://127.0.0.1:8000",
    upscayl_bin: "./tools/upscayl/realesrgan-ncnn-vulkan.exe",
    steps: 6,
    guidance_scale: 1.4,
    upscale_enabled: true,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [serviceStatus, setServiceStatus] = useState(null);
  const [savedBanner, setSavedBanner] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const init = async () => {
      try {
        const [cfg, st] = await Promise.all([
          api.getSettings(),
          api.checkLocalImageHealth(),
        ]);
        setForm(cfg);
        setServiceStatus(st);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSavedBanner("");
    try {
      const updated = await api.saveSettings({
        ...form,
        steps: Number(form.steps),
        guidance_scale: Number(form.guidance_scale),
      });
      setForm(updated);
      const st = await api.checkLocalImageHealth();
      setServiceStatus(st);
      setSavedBanner("Settings saved!");
      if (onSettingsSaved) onSettingsSaved(updated);
      setTimeout(() => setSavedBanner(""), 2500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleCheckServices = async () => {
    setChecking(true);
    setError("");
    try {
      // Save current form values first so check tests the entered URL & binary path
      await api.saveSettings({
        ...form,
        steps: Number(form.steps),
        guidance_scale: Number(form.guidance_scale),
      });
      const st = await api.checkLocalImageHealth();
      setServiceStatus(st);
    } catch (err) {
      setError(err.message);
    } finally {
      setChecking(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 text-center text-slate-400">
        <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-indigo-400" />
        Loading settings...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2.5 text-2xl font-bold text-white">
            <SettingsIcon className="h-6 w-6 text-indigo-400" />
            Image Generation Settings
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Configure local FastSD CPU + Upscayl image pipeline or switch to Gemini API fallback.
          </p>
        </div>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError("")} />

      <form onSubmit={handleSave} className="space-y-6">
        {/* Provider Toggle */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
          <label className="mb-3 block text-sm font-bold text-white">
            Image Provider
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => setForm((f) => ({ ...f, image_provider: "local_sd" }))}
              className={`rounded-xl border p-4 text-left transition ${
                form.image_provider === "local_sd"
                  ? "border-indigo-500 bg-indigo-500/15 text-white ring-1 ring-indigo-500/40"
                  : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700"
              }`}
            >
              <div className="flex items-center gap-2 text-sm font-bold">
                <Cpu className="h-4 w-4 text-indigo-400" />
                Local SD (FastSD CPU + Upscayl)
              </div>
              <p className="mt-1 text-xs text-slate-400">
                100% local SD 1.5 + LCM-LoRA at 512×288, upscaled 4× via Upscayl CLI to 1920×1080.
              </p>
            </button>

            <button
              type="button"
              onClick={() => setForm((f) => ({ ...f, image_provider: "gemini" }))}
              className={`rounded-xl border p-4 text-left transition ${
                form.image_provider === "gemini"
                  ? "border-indigo-500 bg-indigo-500/15 text-white ring-1 ring-indigo-500/40"
                  : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700"
              }`}
            >
              <div className="flex items-center gap-2 text-sm font-bold">
                <Sparkles className="h-4 w-4 text-amber-400" />
                Gemini Image API (Fallback)
              </div>
              <p className="mt-1 text-xs text-slate-400">
                Uses Google Gemini Image API (requires billed Google AI Studio quota).
              </p>
            </button>
          </div>
        </div>

        {/* Local SD Settings */}
        <div className="space-y-5 rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-white">FastSD CPU &amp; Upscayl Settings</h2>
            <button
              type="button"
              onClick={handleCheckServices}
              disabled={checking}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-indigo-500 hover:text-white disabled:opacity-50"
            >
              {checking ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5 text-indigo-400" />
              )}
              Check Local Services
            </button>
          </div>

          {serviceStatus && (
            <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-950/80 p-3.5 text-xs">
              <div className="flex items-start gap-2">
                {serviceStatus.fastsd_ok ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                )}
                <span className={serviceStatus.fastsd_ok ? "text-emerald-300" : "text-amber-200"}>
                  {serviceStatus.fastsd_message}
                </span>
              </div>
              <div className="flex items-start gap-2">
                {serviceStatus.upscayl_ok ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                )}
                <span className={serviceStatus.upscayl_ok ? "text-emerald-300" : "text-amber-200"}>
                  {serviceStatus.upscayl_message}
                </span>
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-300">
              FastSD CPU API URL
            </label>
            <input
              type="text"
              value={form.fastsd_url}
              onChange={(e) => setForm((f) => ({ ...f, fastsd_url: e.target.value }))}
              placeholder="http://127.0.0.1:8000"
              className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300">
              Upscayl CLI Binary Path (upscayl-bin)
            </label>
            <input
              type="text"
              value={form.upscayl_bin}
              onChange={(e) => setForm((f) => ({ ...f, upscayl_bin: e.target.value }))}
              placeholder="C:\Program Files\Upscayl\resources\bin\upscayl-bin.exe"
              className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <div className="flex justify-between text-xs">
                <label className="font-semibold text-slate-300">LCM-LoRA Steps</label>
                <span className="font-bold text-indigo-300">{form.steps} steps</span>
              </div>
              <input
                type="range"
                min="4"
                max="6"
                step="1"
                value={form.steps}
                onChange={(e) => setForm((f) => ({ ...f, steps: Number(e.target.value) }))}
                className="mt-2 h-2 w-full cursor-pointer accent-indigo-500"
              />
              <div className="mt-1 flex justify-between text-[11px] text-slate-500">
                <span>4 (fastest)</span>
                <span>5</span>
                <span>6 (sharper)</span>
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs">
                <label className="font-semibold text-slate-300">Guidance Scale (CFG)</label>
                <span className="font-bold text-indigo-300">
                  {Number(form.guidance_scale).toFixed(1)}
                </span>
              </div>
              <input
                type="range"
                min="1.0"
                max="1.5"
                step="0.1"
                value={form.guidance_scale}
                onChange={(e) =>
                  setForm((f) => ({ ...f, guidance_scale: Number(e.target.value) }))
                }
                className="mt-2 h-2 w-full cursor-pointer accent-indigo-500"
              />
              <div className="mt-1 flex justify-between text-[11px] text-slate-500">
                <span>1.0</span>
                <span>1.2</span>
                <span>1.5</span>
              </div>
            </div>
          </div>

          {/* Upscale Switch */}
          <label className="flex cursor-pointer items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3">
            <div>
              <div className="text-sm font-semibold text-white">
                4× Upscayl Upscaling (512×288 → 1920×1080)
              </div>
              <div className="text-xs text-slate-400">
                Disable if your machine lacks Vulkan support or runs low on VRAM.
              </div>
            </div>
            <input
              type="checkbox"
              checked={Boolean(form.upscale_enabled)}
              onChange={(e) => setForm((f) => ({ ...f, upscale_enabled: e.target.checked }))}
              className="h-5 w-5 rounded border-slate-700 bg-slate-900 accent-indigo-500"
            />
          </label>
        </div>

        <div className="flex items-center justify-end gap-3">
          {savedBanner && (
            <span className="text-xs font-semibold text-emerald-400">{savedBanner}</span>
          )}
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save Settings
          </button>
        </div>
      </form>
    </div>
  );
}
