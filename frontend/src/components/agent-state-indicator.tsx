"use client";

import type { AgentState } from "@/lib/types";
import { STATE_CONFIG } from "@/lib/types";

interface AgentStateIndicatorProps {
  state: AgentState;
}

const GLOW_MAP: Record<string, string> = {
  idle: "",
  initializing: "",
  listening: "glow-blue",
  thinking: "glow-amber",
  speaking: "glow-green",
  filler: "glow-purple",
};

export function AgentStateIndicator({ state }: AgentStateIndicatorProps) {
  const config = STATE_CONFIG[state];
  const glow = GLOW_MAP[state] || "";

  return (
    <div
      className={`glass-strong flex items-center gap-2.5 rounded-full px-4 py-2 ${glow} transition-all duration-500`}
    >
      <div className="relative flex items-center justify-center">
        <div
          className="w-2 h-2 rounded-full transition-colors duration-300"
          style={{ backgroundColor: config.color }}
        />
        {config.pulse && (
          <div
            className="absolute w-2 h-2 rounded-full animate-ping"
            style={{ backgroundColor: config.color, opacity: 0.6 }}
          />
        )}
      </div>
      <span
        className="text-xs font-mono uppercase tracking-widest transition-colors duration-300"
        style={{ color: config.color }}
      >
        {config.label}
      </span>
    </div>
  );
}
