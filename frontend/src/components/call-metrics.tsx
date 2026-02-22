"use client";

import { useState, useEffect, useMemo } from "react";
import type { CallMetricsData } from "@/lib/types";

interface CallMetricsProps {
  isLive: boolean;
  metrics: CallMetricsData | null;
  callStartTime: number | null;
}

const STAGE_LABELS: Record<string, string> = {
  greeting: "Begr\u00fc\u00dfung",
  qualification: "Qualifizierung",
  pitch: "Pitch",
  objection_handling: "Einwandbehandlung",
  closing: "Abschluss",
  follow_up: "Follow-Up",
};

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return [h, m, s].map((v) => String(v).padStart(2, "0")).join(":");
}

function getScoreColor(score: number): string {
  if (score <= 30) return "#ef4444";
  if (score <= 60) return "#f59e0b";
  if (score <= 80) return "#22c55e";
  return "#3b82f6";
}

function LeadScoreRing({ score }: { score: number }) {
  const size = 44;
  const strokeWidth = 3.5;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = getScoreColor(score);

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Background ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={strokeWidth}
        />
        {/* Progress ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 0.6s ease, stroke 0.4s ease" }}
        />
      </svg>
      <span
        className="absolute text-[11px] font-mono font-semibold"
        style={{ color }}
      >
        {score}
      </span>
    </div>
  );
}

function SkeletonBlock({ width }: { width: string }) {
  return (
    <div
      className="h-4 rounded-md animate-pulse"
      style={{
        width,
        background: "rgba(255,255,255,0.06)",
      }}
    />
  );
}

function Divider() {
  return (
    <div
      className="self-stretch w-px mx-1"
      style={{ background: "rgba(255,255,255,0.06)" }}
    />
  );
}

function MoodArrow({ trajectory }: { trajectory: string }) {
  if (trajectory === "improving") {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path
          d="M8 12V4M8 4L4.5 7.5M8 4L11.5 7.5"
          stroke="#22c55e"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (trajectory === "declining") {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path
          d="M8 4V12M8 12L4.5 8.5M8 12L11.5 8.5"
          stroke="#ef4444"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  // stable / unknown
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path
        d="M4 8H12"
        stroke="rgba(255,255,255,0.3)"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function getMoodLabel(trajectory: string): string {
  if (trajectory === "improving") return "Steigend";
  if (trajectory === "declining") return "Fallend";
  return "Stabil";
}

function getMoodColor(trajectory: string): string {
  if (trajectory === "improving") return "#22c55e";
  if (trajectory === "declining") return "#ef4444";
  return "rgba(255,255,255,0.3)";
}

export function CallMetrics({ isLive, metrics, callStartTime }: CallMetricsProps) {
  const [elapsed, setElapsed] = useState(0);

  // Live timer
  useEffect(() => {
    if (!isLive || callStartTime === null) {
      setElapsed(0);
      return;
    }

    const tick = () => {
      setElapsed(Math.max(0, Math.floor(Date.now() / 1000 - callStartTime)));
    };

    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [isLive, callStartTime]);

  // Response time bar width (capped at 2000ms)
  const responseBarWidth = useMemo(() => {
    if (!metrics) return 0;
    return Math.min(100, (metrics.avg_response_time_ms / 2000) * 100);
  }, [metrics]);

  const responseTimeColor = useMemo(() => {
    if (!metrics) return "#22c55e";
    if (metrics.avg_response_time_ms <= 500) return "#22c55e";
    if (metrics.avg_response_time_ms <= 1000) return "#f59e0b";
    return "#ef4444";
  }, [metrics]);

  if (!isLive) return null;

  const isLoading = metrics === null;

  return (
    <div className="glass rounded-2xl px-4 py-3 flex items-center gap-3 overflow-x-auto">
      {/* Call Duration */}
      <div className="flex flex-col items-center min-w-[70px]">
        <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest mb-1">
          Dauer
        </span>
        <span className="text-[15px] font-mono font-semibold text-white/90 tabular-nums">
          {formatDuration(elapsed)}
        </span>
      </div>

      <Divider />

      {/* Lead Score */}
      <div className="flex flex-col items-center min-w-[54px]">
        <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest mb-1">
          Score
        </span>
        {isLoading ? (
          <SkeletonBlock width="44px" />
        ) : (
          <LeadScoreRing score={metrics.lead_score} />
        )}
      </div>

      <Divider />

      {/* Response Time */}
      <div className="flex flex-col items-center min-w-[72px]">
        <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest mb-1">
          Antwort
        </span>
        {isLoading ? (
          <SkeletonBlock width="50px" />
        ) : (
          <div className="flex flex-col items-center gap-1">
            <span className="text-[13px] font-mono font-semibold text-white/85">
              {Math.round(metrics.avg_response_time_ms)}
              <span className="text-[9px] text-white/50 ml-0.5">ms</span>
            </span>
            <div
              className="h-[3px] rounded-full"
              style={{
                width: 48,
                background: "rgba(255,255,255,0.06)",
              }}
            >
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${responseBarWidth}%`,
                  background: responseTimeColor,
                }}
              />
            </div>
          </div>
        )}
      </div>

      <Divider />

      {/* Turns */}
      <div className="flex flex-col items-center min-w-[60px]">
        <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest mb-1">
          Turns
        </span>
        {isLoading ? (
          <SkeletonBlock width="40px" />
        ) : (
          <div className="flex items-baseline gap-0.5">
            <span className="text-[13px] font-mono font-semibold text-blue-400/90">
              {metrics.user_turns}
            </span>
            <span className="text-[10px] font-mono text-white/40">/</span>
            <span className="text-[13px] font-mono font-semibold text-green-400/90">
              {metrics.agent_turns}
            </span>
          </div>
        )}
      </div>

      <Divider />

      {/* Stage */}
      <div className="flex flex-col items-center min-w-[90px]">
        <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest mb-1">
          Phase
        </span>
        {isLoading ? (
          <SkeletonBlock width="70px" />
        ) : (
          <span className="text-[11px] font-mono font-medium text-purple-400/90 truncate max-w-[110px]">
            {STAGE_LABELS[metrics.current_stage] ?? metrics.current_stage}
          </span>
        )}
      </div>

      <Divider />

      {/* Mood Trend */}
      <div className="flex flex-col items-center min-w-[52px]">
        <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest mb-1">
          Trend
        </span>
        {isLoading ? (
          <SkeletonBlock width="30px" />
        ) : (
          <div className="flex items-center gap-1">
            <MoodArrow trajectory={metrics.mood_trajectory} />
            <span
              className="text-[9px] font-mono font-medium"
              style={{ color: getMoodColor(metrics.mood_trajectory) }}
            >
              {getMoodLabel(metrics.mood_trajectory)}
            </span>
          </div>
        )}
      </div>

      {/* Objections — only show if any detected */}
      {!isLoading && metrics.objection_count > 0 && (
        <>
          <Divider />
          <div className="flex flex-col items-center min-w-[48px]">
            <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest mb-1">
              Einwände
            </span>
            <div className="flex items-center gap-1">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path
                  d="M8 5v3m0 2.5h.01M14 8A6 6 0 112 8a6 6 0 0112 0z"
                  stroke="#f59e0b"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span className="text-[13px] font-mono font-semibold text-amber-400/90">
                {metrics.objection_count}
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
