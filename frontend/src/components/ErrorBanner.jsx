import React from "react";
import { AlertCircle, X } from "lucide-react";

export default function ErrorBanner({ error, onDismiss }) {
  if (!error) return null;
  return (
    <div className="mb-6 flex items-start justify-between gap-3 rounded-xl border border-rose-500/40 bg-rose-950/50 px-4 py-3 text-sm text-rose-200 shadow-lg">
      <div className="flex items-start gap-2.5">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
        <div>
          <p className="font-semibold text-rose-100">Action Required / API Error</p>
          <p className="mt-0.5 leading-relaxed text-rose-200/90">{error}</p>
        </div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="rounded-lg p-1 text-rose-300 transition hover:bg-rose-900/60 hover:text-white"
          aria-label="Dismiss error"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
