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

  const { points, pathD, areaD } = useMemo(() => {
    if (data.length < 1) return { points: [], pathD: "", areaD: "" };
    const tMin = data[0].timestamp;
    const tRange = (data[data.length - 1].timestamp - tMin) || 1;
    const pts = data.map((d) => ({
      x: pad.left + ((d.timestamp - tMin) / tRange) * gw,
      y: pad.top + getMoodY(d.mood) * gh,
      mood: d.mood,
    }));
    const pD = smoothPath(pts);
    const aD = pD
      ? `${pD} L ${pts[pts.length - 1].x} ${pad.top + gh} L ${pts[0].x} ${pad.top + gh} Z`
      : "";
    return { points: pts, pathD: pD, areaD: aD };
  }, [data, gw, gh, pad.left, pad.top]);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-auto"
      style={{ minHeight: 180 }}
    >
      <defs>
        {/* Gradient fill under the curve */}
        <linearGradient id="area-gradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.2" />
          <stop offset="50%" stopColor="#8b5cf6" stopOpacity="0.08" />
          <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" />
        </linearGradient>
        {/* Glow filter for dots */}
        <filter id="dot-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        {/* Line gradient */}
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
      {areaD && (
        <path d={areaD} fill="url(#area-gradient)" />
      )}

      {/* Line */}
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

      {/* Data points */}
      {points.map((pt, i) => {
        const color = MOOD_COLORS[pt.mood];
        return (
          <g key={i} filter="url(#dot-glow)">
            {/* Outer ring */}
            <circle
              cx={pt.x}
              cy={pt.y}
              r="6"
              fill="none"
              stroke={color}
              strokeWidth="1.5"
              opacity="0.4"
            />
            {/* Inner dot */}
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
  );
}
