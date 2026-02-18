"use client";

import { useEffect, useRef } from "react";
import type { TranscriptEntry } from "@/lib/types";
import { MOOD_COLORS } from "@/lib/types";

interface TranscriptViewProps {
  entries: TranscriptEntry[];
}

export function TranscriptView({ entries }: TranscriptViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [entries]);

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 gap-3">
        <div className="w-10 h-10 rounded-full glass flex items-center justify-center">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5">
            <path d="M12 18.5C15.59 18.5 18.5 15.59 18.5 12C18.5 8.41 15.59 5.5 12 5.5C8.41 5.5 5.5 8.41 5.5 12C5.5 15.59 8.41 18.5 12 18.5Z" />
            <path d="M19.14 19.14L17.01 17.01" />
          </svg>
        </div>
        <span className="text-white/20 text-xs font-mono">
          Warten auf Gespräch...
        </span>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="space-y-3 overflow-y-auto pr-1"
      style={{ maxHeight: "calc(100vh - 380px)", minHeight: 200 }}
    >
      {entries.map((entry, i) => {
        const isAgent = entry.speaker === "agent";
        return (
          <div
            key={i}
            className={`flex ${isAgent ? "justify-start" : "justify-end"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed transition-all duration-200 ${
                isAgent
                  ? "glass rounded-bl-md text-white/85"
                  : "bg-blue-500/10 border border-blue-500/15 rounded-br-md text-blue-100/90"
              }`}
            >
              {/* Header */}
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`text-[9px] font-mono font-semibold uppercase tracking-wider ${
                    isAgent ? "text-white/30" : "text-blue-400/50"
                  }`}
                >
                  {isAgent ? "Agent" : "Anrufer"}
                </span>
                {entry.mood && (
                  <span
                    className="text-[9px] font-mono font-medium rounded-full px-1.5 py-px"
                    style={{
                      color: MOOD_COLORS[entry.mood],
                      backgroundColor: `${MOOD_COLORS[entry.mood]}15`,
                    }}
                  >
                    {entry.mood}
                  </span>
                )}
              </div>
              {entry.text}
            </div>
          </div>
        );
      })}
    </div>
  );
}
