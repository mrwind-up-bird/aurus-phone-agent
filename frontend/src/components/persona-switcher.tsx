"use client";

import { PERSONAS } from "@/lib/types";

interface PersonaSwitcherProps {
  activePersona: string;
  onSwitch: (key: string) => void;
}

const PERSONA_ICONS: Record<string, string> = {
  lukas: "L",
  sarah: "S",
  marcus: "M",
};

const PERSONA_COLORS: Record<string, string> = {
  lukas: "#3b82f6",
  sarah: "#ec4899",
  marcus: "#22c55e",
};

export function PersonaSwitcher({
  activePersona,
  onSwitch,
}: PersonaSwitcherProps) {
  return (
    <div className="flex gap-3">
      {PERSONAS.map((persona) => {
        const isActive = persona.key === activePersona;
        const color = PERSONA_COLORS[persona.key] || "#3b82f6";
        return (
          <button
            key={persona.key}
            onClick={() => onSwitch(persona.key)}
            className={`group relative flex items-center gap-3 rounded-xl px-4 py-3 transition-all duration-300 ${
              isActive
                ? "glass-strong"
                : "glass hover:glass-strong"
            }`}
            style={
              isActive
                ? {
                    boxShadow: `0 0 24px ${color}20, 0 0 60px ${color}08`,
                    borderColor: `${color}30`,
                  }
                : undefined
            }
          >
            {/* Avatar */}
            <div
              className="flex items-center justify-center w-8 h-8 rounded-lg text-xs font-bold transition-all duration-300"
              style={{
                backgroundColor: isActive ? `${color}20` : "rgba(255,255,255,0.05)",
                color: isActive ? color : "rgba(255,255,255,0.4)",
              }}
            >
              {PERSONA_ICONS[persona.key]}
            </div>
            {/* Info */}
            <div className="text-left">
              <div
                className="text-sm font-semibold transition-colors duration-300"
                style={{ color: isActive ? color : "rgba(255,255,255,0.7)" }}
              >
                {persona.name}
              </div>
              <div className="text-[10px] text-white/30 font-mono">
                {persona.role}
              </div>
            </div>
            {/* Active dot */}
            {isActive && (
              <div
                className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: color }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
