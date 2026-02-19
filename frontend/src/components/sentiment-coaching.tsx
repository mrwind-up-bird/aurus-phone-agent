"use client";

import { useMemo } from "react";
import type { MoodDataPoint, RequiredTone, UserMood } from "@/lib/types";
import { computeAvgScore } from "./sentiment-graph";

interface CoachingHint {
  id: string;
  text: string;
  icon: string;
  color: string;
  priority: number;
}

const TONE_OPTIONS: { tone: RequiredTone; label: string; color: string }[] = [
  { tone: "professional", label: "Professionell", color: "#3b82f6" },
  { tone: "enthusiastic", label: "Begeistert", color: "#22c55e" },
  { tone: "reassuring", label: "Beruhigend", color: "#a855f7" },
  { tone: "empathetic", label: "Einf\u00fchlsam", color: "#f472b6" },
  { tone: "urgent", label: "Dringlich", color: "#ef4444" },
  { tone: "neutral", label: "Neutral", color: "#94a3b8" },
];

const MOOD_SCORES: Record<UserMood, number> = {
  enthusiastic: 3,
  interested: 2,
  neutral: 1,
  confused: 0,
  skeptical: -1,
  frustrated: -2,
  dismissive: -3,
};

interface SentimentCoachingProps {
  moodHistory: MoodDataPoint[];
  activeTone: RequiredTone;
  onToneShift: (tone: RequiredTone) => void;
  isLive: boolean;
}

function getTrajectory(
  data: MoodDataPoint[]
): "rising" | "declining" | "stable" {
  if (data.length < 3) return "stable";
  const recent = data.slice(-3);
  const first = MOOD_SCORES[recent[0].mood];
  const last = MOOD_SCORES[recent[recent.length - 1].mood];
  const diff = last - first;
  if (diff >= 1.5) return "rising";
  if (diff <= -1.5) return "declining";
  return "stable";
}

function generateHints(data: MoodDataPoint[]): CoachingHint[] {
  if (data.length === 0) return [];

  const current = data[data.length - 1].mood;
  const trajectory = getTrajectory(data);
  const avg = computeAvgScore(data);
  const hints: CoachingHint[] = [];

  if (current === "skeptical" && trajectory === "declining") {
    hints.push({
      id: "skeptical-declining",
      text: "Vertrauen aufbauen \u2014 konkrete Referenzen nennen",
      icon: "\u{1f6e1}",
      color: "#f59e0b",
      priority: 1,
    });
  } else if (current === "skeptical") {
    hints.push({
      id: "skeptical",
      text: "Bedenken ernst nehmen \u2014 mit Fakten \u00fcberzeugen",
      icon: "\u{1f4ca}",
      color: "#f59e0b",
      priority: 2,
    });
  }

  if (current === "frustrated") {
    hints.push({
      id: "frustrated",
      text: "Tempo reduzieren \u2014 aktiv zuh\u00f6ren, Verst\u00e4ndnis zeigen",
      icon: "\u26a0",
      color: "#ef4444",
      priority: 0,
    });
  }

  if (current === "enthusiastic") {
    hints.push({
      id: "enthusiastic",
      text: "Momentum nutzen \u2014 zum Abschluss \u00fcberleiten",
      icon: "\u{1f3af}",
      color: "#22c55e",
      priority: 2,
    });
  }

  if (current === "confused") {
    hints.push({
      id: "confused",
      text: "Vereinfachen \u2014 Kernbotschaft wiederholen",
      icon: "\u{1f4a1}",
      color: "#a855f7",
      priority: 1,
    });
  }

  if (current === "dismissive") {
    hints.push({
      id: "dismissive",
      text: "Respektvoll verabschieden \u2014 Unterlagen anbieten",
      icon: "\u{1f4cb}",
      color: "#6b7280",
      priority: 0,
    });
  }

  if (current === "interested" && trajectory === "rising") {
    hints.push({
      id: "interested-rising",
      text: "Interesse vertiefen \u2014 Demo oder Termin vorschlagen",
      icon: "\u{1f4c8}",
      color: "#22c55e",
      priority: 2,
    });
  }

  // Average-based hint
  if (avg.score < -0.5) {
    hints.push({
      id: "avg-low",
      text: "Gespr\u00e4chsstrategie \u00fcberdenken \u2014 offene Fragen stellen",
      icon: "\u{1f504}",
      color: "#f59e0b",
      priority: 1,
    });
  }

  return hints.sort((a, b) => a.priority - b.priority).slice(0, 2);
}

export function SentimentCoaching({
  moodHistory,
  activeTone,
  onToneShift,
  isLive,
}: SentimentCoachingProps) {
  const hints = useMemo(() => generateHints(moodHistory), [moodHistory]);

  return (
    <div className="glass rounded-2xl p-5" data-tone-shift>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Coaching Hints */}
        <div>
          <h3 className="text-[11px] font-mono text-white/30 uppercase tracking-widest mb-3">
            Coaching-Hinweise
          </h3>
          <div className="space-y-2 min-h-[72px]">
            {hints.length > 0 ? (
              hints.map((hint) => (
                <div
                  key={hint.id}
                  className="flex items-start gap-3 rounded-xl px-3.5 py-2.5 transition-all duration-500"
                  style={{
                    background: `${hint.color}10`,
                    borderLeft: `2px solid ${hint.color}40`,
                    animation: "fadeSlideIn 0.4s ease-out",
                  }}
                >
                  <span
                    className="text-sm mt-0.5 shrink-0"
                    style={{ filter: "saturate(0.8)" }}
                  >
                    {hint.icon}
                  </span>
                  <span
                    className="text-xs leading-relaxed"
                    style={{ color: `${hint.color}cc` }}
                  >
                    {hint.text}
                  </span>
                </div>
              ))
            ) : (
              <div className="flex items-center justify-center h-[72px] text-white/15 text-xs font-mono">
                Keine Hinweise
              </div>
            )}
          </div>
        </div>

        {/* Tone Shift Buttons */}
        <div>
          <h3 className="text-[11px] font-mono text-white/30 uppercase tracking-widest mb-3">
            Ton-Steuerung
            {!isLive && (
              <span className="ml-2 text-amber-400/50">(Demo)</span>
            )}
          </h3>
          <div className="grid grid-cols-3 gap-2">
            {TONE_OPTIONS.map(({ tone, label, color }) => {
              const isActive = activeTone === tone;
              return (
                <button
                  key={tone}
                  onClick={() => onToneShift(tone)}
                  className="relative rounded-xl px-3 py-2 text-[11px] font-medium transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                  style={{
                    background: isActive
                      ? `${color}20`
                      : "rgba(255,255,255,0.03)",
                    border: `1px solid ${isActive ? `${color}40` : "rgba(255,255,255,0.06)"}`,
                    color: isActive ? color : "rgba(255,255,255,0.4)",
                    boxShadow: isActive ? `0 0 12px ${color}15` : "none",
                  }}
                >
                  {isActive && (
                    <span
                      className="absolute top-1 right-1.5 w-1.5 h-1.5 rounded-full"
                      style={{ background: color }}
                    />
                  )}
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
