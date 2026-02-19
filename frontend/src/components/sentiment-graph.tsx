"use client";

import { useMemo } from "react";
import type { MoodDataPoint, UserMood } from "@/lib/types";
import { MOOD_COLORS } from "@/lib/types";

interface SentimentGraphProps {
  data: MoodDataPoint[];
}

const MOOD_LEVELS: { mood: UserMood; label: string; y: number }[] = [
  { mood: "enthusiastic", label: "Begeistert", y: 0.08 },
  { mood: "interested", label: "Interessiert", y: 0.25 },
  { mood: "neutral", label: "Neutral", y: 0.45 },
  { mood: "confused", label: "Verwirrt", y: 0.6 },
  { mood: "skeptical", label: "Skeptisch", y: 0.72 },
  { mood: "frustrated", label: "Frustriert", y: 0.85 },
  { mood: "dismissive", label: "Ablehnend", y: 0.95 },
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

/** Map a numeric score to a Y position (interpolated between mood levels). */
function scoreToY(score: number): number {
  const mapping = [
    { score: 3, y: 0.08 },
    { score: 2, y: 0.25 },
    { score: 1, y: 0.45 },
    { score: 0, y: 0.6 },
    { score: -1, y: 0.72 },
    { score: -2, y: 0.85 },
    { score: -3, y: 0.95 },
  ];
  if (score >= 3) return 0.08;
  if (score <= -3) return 0.95;
  for (let i = 0; i < mapping.length - 1; i++) {
    if (score <= mapping[i].score && score >= mapping[i + 1].score) {
      const t =
        (mapping[i].score - score) / (mapping[i].score - mapping[i + 1].score);
      return mapping[i].y + t * (mapping[i + 1].y - mapping[i].y);
    }
  }
  return 0.45;
}

/** Compute the rolling average score, label, and color for the last N mood data points. */
export function computeAvgScore(
  data: MoodDataPoint[],
  window = 5
): { score: number; label: string; color: string } {
  if (data.length === 0) return { score: 0, label: "\u2014", color: "#94a3b8" };
  const recent = data.slice(-window);
  const avg =
    recent.reduce((sum, d) => sum + MOOD_SCORES[d.mood], 0) / recent.length;
  if (avg >= 2.5) return { score: avg, label: "Begeistert", color: "#3b82f6" };
  if (avg >= 1.5)
    return { score: avg, label: "Interessiert", color: "#22c55e" };
  if (avg >= 0.5) return { score: avg, label: "Neutral", color: "#94a3b8" };
  if (avg >= -0.5) return { score: avg, label: "Verwirrt", color: "#a855f7" };
  if (avg >= -1.5)
    return { score: avg, label: "Skeptisch", color: "#f59e0b" };
  if (avg >= -2.5)
    return { score: avg, label: "Frustriert", color: "#ef4444" };
  return { score: avg, label: "Ablehnend", color: "#6b7280" };
}

function getMoodY(mood: UserMood): number {
  return MOOD_LEVELS.find((m) => m.mood === mood)?.y ?? 0.45;
}

function smoothPath(points: { x: number; y: number }[]): string {
  if (points.length < 2) return "";
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const cpx = (prev.x + curr.x) / 2;
    d += ` C ${cpx} ${prev.y}, ${cpx} ${curr.y}, ${curr.x} ${curr.y}`;
  }
  return d;
}

export function SentimentGraph({ data }: SentimentGraphProps) {
  const width = 600;
  const height = 220;
  const pad = { top: 16, bottom: 16, left: 90, right: 24 };
  const gw = width - pad.left - pad.right;
  const gh = height - pad.top - pad.bottom;

  const { points, pathD, areaD, avgPathD } = useMemo(() => {
    if (data.length < 1)
      return { points: [], pathD: "", areaD: "", avgPathD: "" };
    const tMin = data[0].timestamp;
    const tRange = data[data.length - 1].timestamp - tMin || 1;
    const pts = data.map((d) => ({
      x: pad.left + ((d.timestamp - tMin) / tRange) * gw,
      y: pad.top + getMoodY(d.mood) * gh,
      mood: d.mood,
    }));
    const pD = smoothPath(pts);
    const aD = pD
      ? `${pD} L ${pts[pts.length - 1].x} ${pad.top + gh} L ${pts[0].x} ${pad.top + gh} Z`
      : "";

    // Rolling average line
    const avgPts = data.map((d, i) => {
      const windowStart = Math.max(0, i - 4);
      const windowData = data.slice(windowStart, i + 1);
      const avgScore =
        windowData.reduce((sum, p) => sum + MOOD_SCORES[p.mood], 0) /
        windowData.length;
      return {
        x: pad.left + ((d.timestamp - tMin) / tRange) * gw,
        y: pad.top + scoreToY(avgScore) * gh,
      };
    });
    const avgD = smoothPath(avgPts);

    return { points: pts, pathD: pD, areaD: aD, avgPathD: avgD };
  }, [data, gw, gh, pad.left, pad.top]);

  const avg = useMemo(() => computeAvgScore(data), [data]);

  return (
    <div className="relative">
      {/* Average badge — top right */}
      {data.length > 0 && (
        <div className="absolute top-0 right-0 flex items-center gap-2 z-10">
          <div
            className="rounded-lg px-2.5 py-1 text-[10px] font-mono flex items-center gap-1.5"
            style={{
              background: `${avg.color}15`,
              border: `1px solid ${avg.color}30`,
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: avg.color }}
            />
            <span style={{ color: `${avg.color}cc` }}>{avg.label}</span>
            <span style={{ color: `${avg.color}80` }}>
              {avg.score.toFixed(1)}
            </span>
          </div>
        </div>
      )}

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto"
        style={{ minHeight: 180 }}
      >
        <defs>
          <linearGradient id="area-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.2" />
            <stop offset="50%" stopColor="#8b5cf6" stopOpacity="0.08" />
            <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" />
          </linearGradient>
          <filter id="dot-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="line-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="50%" stopColor="#8b5cf6" />
            <stop offset="100%" stopColor="#22c55e" />
          </linearGradient>
        </defs>

        {/* Grid lines + labels */}
        {MOOD_LEVELS.map((level) => {
          const y = pad.top + level.y * gh;
          return (
            <g key={level.mood}>
              <line
                x1={pad.left}
                y1={y}
                x2={width - pad.right}
                y2={y}
                stroke="rgba(255,255,255,0.04)"
                strokeWidth="1"
                className="sentiment-grid-line"
              />
              <text
                x={pad.left - 10}
                y={y + 4}
                textAnchor="end"
                fill="rgba(255,255,255,0.3)"
                fontSize="10"
                fontFamily="var(--font-geist-mono)"
              >
                {level.label}
              </text>
            </g>
          );
        })}

        {/* Area fill */}
        {areaD && <path d={areaD} fill="url(#area-gradient)" />}

        {/* Main mood line */}
        {pathD && (
          <path
            d={pathD}
            fill="none"
            stroke="url(#line-gradient)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {/* Rolling average line (dashed, amber) */}
        {avgPathD && (
          <path
            d={avgPathD}
            fill="none"
            stroke="#f59e0b"
            strokeWidth="1.5"
            strokeDasharray="6 4"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.5"
          />
        )}

        {/* Data points */}
        {points.map((pt, i) => {
          const color = MOOD_COLORS[pt.mood];
          return (
            <g key={i} filter="url(#dot-glow)">
              <circle
                cx={pt.x}
                cy={pt.y}
                r="6"
                fill="none"
                stroke={color}
                strokeWidth="1.5"
                opacity="0.4"
              />
              <circle cx={pt.x} cy={pt.y} r="3" fill={color} />
            </g>
          );
        })}

        {/* Empty state */}
        {data.length === 0 && (
          <text
            x={width / 2}
            y={height / 2}
            textAnchor="middle"
            fill="rgba(255,255,255,0.2)"
            fontSize="13"
            fontFamily="var(--font-geist-mono)"
          >
            Warten auf Stimmungsdaten...
          </text>
        )}
      </svg>
    </div>
  );
}
