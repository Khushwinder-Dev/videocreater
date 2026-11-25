import React from "react";
import { Check } from "lucide-react";

const STEPS = [
  { id: 1, label: "Setup" },
  { id: 2, label: "Topics" },
  { id: 3, label: "Script" },
  { id: 4, label: "Scenes" },
  { id: 5, label: "Voiceover" },
  { id: 6, label: "Images" },
  { id: 7, label: "Render" },
  { id: 8, label: "YouTube" },
];

export default function WizardStepper({ activeStep, maxReachedStep, onStepClick }) {
  return (
    <div className="border-b border-slate-800/80 bg-slate-900/50">
      <div className="mx-auto max-w-7xl px-4 py-3 sm:px-6">
        <nav aria-label="Wizard Progress" className="grid grid-cols-4 gap-2 sm:grid-cols-8">
          {STEPS.map((step) => {
            const isActive = step.id === activeStep;
            const isCompleted = step.id < activeStep;
            const isReachable = step.id <= maxReachedStep;

            return (
              <button
                key={step.id}
                type="button"
                disabled={!isReachable}
                onClick={() => isReachable && onStepClick(step.id)}
                className={`group flex items-center gap-2 rounded-lg px-2.5 py-2 text-left transition ${
                  isActive
                    ? "bg-indigo-600/20 text-indigo-300 ring-1 ring-indigo-500/50"
                    : isReachable
                    ? "bg-slate-800/40 text-slate-300 hover:bg-slate-800 hover:text-white"
                    : "cursor-not-allowed bg-slate-900/30 text-slate-600"
                }`}
              >
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    isActive
                      ? "bg-indigo-500 text-white"
                      : isCompleted
                      ? "bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/40"
                      : isReachable
                      ? "bg-slate-700 text-slate-200"
                      : "bg-slate-800 text-slate-600"
                  }`}
                >
                  {isCompleted ? <Check className="h-3.5 w-3.5" /> : step.id}
                </span>
                <span className="truncate text-xs font-semibold">{step.label}</span>
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
