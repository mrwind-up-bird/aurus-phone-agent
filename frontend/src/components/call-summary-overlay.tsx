"use client";

import type { CallSummaryData } from "@/lib/types";

interface CallSummaryOverlayProps {
  summary: CallSummaryData;
  onDismiss: () => void;
}

const OUTCOME_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  booked: { label: "Termin gebucht", color: "#22c55e", icon: "M9 12l2 2 4-4" },
  interested: { label: "Interesse geweckt", color: "#3b82f6", icon: "M12 4v16m0-16l-4 4m4-4l4 4" },
  declined: { label: "Abgelehnt", color: "#ef4444", icon: "M18 6L6 18M6 6l12 12" },
  end_call: { label: "Gespräch beendet", color: "#94a3b8", icon: "M6 18L18 6" },
};

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

function getScoreColor(score: number): string {
  if (score <= 30) return "#ef4444";
  if (score <= 60) return "#f59e0b";
  if (score <= 80) return "#22c55e";
  return "#3b82f6";
}

function getMoodLabel(trajectory: string): string {
  if (trajectory === "improving") return "Steigend";
  if (trajectory === "declining") return "Fallend";
  return "Stabil";
}

export function CallSummaryOverlay({ summary, onDismiss }: CallSummaryOverlayProps) {
  const outcome = OUTCOME_CONFIG[summary.outcome] ?? OUTCOME_CONFIG.end_call;
  const scoreColor = getScoreColor(summary.lead_score);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onDismiss}
      />

      {/* Card */}
      <div
        className="relative glass rounded-3xl p-8 max-w-md w-full animate-in fade-in zoom-in-95 duration-300"
        style={{ border: `1px solid ${outcome.color}20` }}
      >
        {/* Close */}
        <button
          onClick={onDismiss}
          className="absolute top-4 right-4 text-white/30 hover:text-white/60 transition"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
          </svg>
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: `${outcome.color}15` }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={outcome.color} strokeWidth="2">
              <path d={outcome.icon} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white/90">Anruf beendet</h3>
            <span
              className="text-[11px] font-mono font-medium"
              style={{ color: outcome.color }}
            >
              {outcome.label}
            </span>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="text-center">
            <div className="text-[10px] font-mono text-white/25 uppercase tracking-widest mb-1">
              Score
            </div>
            <div className="text-2xl font-mono font-bold" style={{ color: scoreColor }}>
              {summary.lead_score}
            </div>
          </div>
          <div className="text-center">
            <div className="text-[10px] font-mono text-white/25 uppercase tracking-widest mb-1">
              Dauer
            </div>
            <div className="text-lg font-mono font-semibold text-white/85">
              {formatDuration(summary.duration_seconds)}
            </div>
          </div>
          <div className="text-center">
            <div className="text-[10px] font-mono text-white/25 uppercase tracking-widest mb-1">
              Trend
            </div>
            <div className="text-lg font-mono font-semibold text-white/85">
              {getMoodLabel(summary.mood_trajectory)}
            </div>
          </div>
        </div>

        {/* Summary text */}
        <div className="glass rounded-xl p-4 mb-6">
          <div className="text-[10px] font-mono text-white/25 uppercase tracking-widest mb-2">
            KI-Zusammenfassung
          </div>
          <p className="text-sm text-white/70 leading-relaxed">
            {summary.summary}
          </p>
        </div>

        {/* Turns */}
        <div className="flex items-center justify-between text-[11px] font-mono text-white/30">
          <span>{summary.turn_count} Gesprächsrunden</span>
          <span>Automatisch gespeichert</span>
        </div>
      </div>
    </div>
  );
}
