"use client";

import { useEffect, useRef } from "react";
import { useConversations } from "@/hooks/use-conversations";
import { TranscriptView } from "@/components/transcript-view";
import { PERSONAS } from "@/lib/types";
import type { ConversationSummary, ConversationDetail as ConvDetail } from "@/lib/types";

interface ConversationHistoryProps {
  open: boolean;
  onClose: () => void;
}

const PERSONA_COLORS: Record<string, string> = {
  lukas: "#3b82f6",
  sarah: "#ec4899",
  marcus: "#22c55e",
  // Stored conversations use persona NAME (capitalized), so include both forms
  Lukas: "#3b82f6",
  Sarah: "#ec4899",
  Marcus: "#22c55e",
};

const OUTCOME_STYLES: Record<string, { bg: string; text: string }> = {
  booked: { bg: "rgba(34,197,94,0.12)", text: "#22c55e" },
  interested: { bg: "rgba(59,130,246,0.12)", text: "#3b82f6" },
  callback: { bg: "rgba(245,158,11,0.12)", text: "#f59e0b" },
  declined: { bg: "rgba(239,68,68,0.10)", text: "#ef4444" },
  voicemail: { bg: "rgba(107,114,128,0.12)", text: "#6b7280" },
  "no-answer": { bg: "rgba(107,114,128,0.12)", text: "#6b7280" },
};

function getOutcomeStyle(outcome: string) {
  return (
    OUTCOME_STYLES[outcome.toLowerCase()] || {
      bg: "rgba(255,255,255,0.06)",
      text: "rgba(255,255,255,0.5)",
    }
  );
}

function formatDateTime(isoString: string): { date: string; time: string } {
  try {
    const d = new Date(isoString);
    return {
      date: d.toLocaleDateString("de-DE", {
        day: "2-digit",
        month: "2-digit",
        year: "2-digit",
      }),
      time: d.toLocaleTimeString("de-DE", {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };
  } catch {
    return { date: "--", time: "--" };
  }
}

function getPersonaInitial(personaKey: string): string {
  const persona = PERSONAS.find((p) => p.key === personaKey);
  return persona ? persona.name.charAt(0).toUpperCase() : personaKey.charAt(0).toUpperCase();
}

function getPersonaName(personaKey: string): string {
  const persona = PERSONAS.find((p) => p.key === personaKey);
  return persona ? persona.name : personaKey;
}

export function ConversationHistory({ open, onClose }: ConversationHistoryProps) {
  const {
    conversations,
    selectedConversation,
    loadDetail,
    refresh,
    isLoading,
    isLoadingDetail,
    clearSelection,
  } = useConversations();

  const panelRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  // Close on escape key
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  // Reset selection when panel closes
  useEffect(() => {
    if (!open) {
      clearSelection();
    }
  }, [open, clearSelection]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        ref={backdropRef}
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={onClose}
      />

      {/* Slide-out panel */}
      <div
        ref={panelRef}
        className="fixed top-0 right-0 z-50 h-full w-full max-w-lg glass-strong flex flex-col animate-in slide-in-from-right duration-300"
        style={{
          boxShadow: "-8px 0 40px rgba(0,0,0,0.3), -2px 0 20px rgba(59,130,246,0.05)",
        }}
      >
        {/* Panel header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-white/[0.06]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="rgba(59,130,246,0.7)"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white/90">
                Gesprächsverlauf
              </h2>
              <p className="text-[10px] font-mono text-white/50 uppercase tracking-widest">
                {conversations.length} Gespräche
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Refresh button */}
            <button
              onClick={refresh}
              disabled={isLoading}
              className="glass rounded-lg p-2 text-white/55 hover:text-white/60 hover:bg-white/5 transition-all duration-200"
              title="Aktualisieren"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={isLoading ? "animate-spin" : ""}
              >
                <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
              </svg>
            </button>

            {/* Close button */}
            <button
              onClick={onClose}
              className="glass rounded-lg p-2 text-white/55 hover:text-white/60 hover:bg-white/5 transition-all duration-200"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              >
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Panel content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {/* Back button when viewing detail */}
          {selectedConversation && (
            <button
              onClick={clearSelection}
              className="flex items-center gap-2 text-xs font-mono text-blue-400/70 hover:text-blue-400 transition-colors mb-2"
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Zurück zur Liste
            </button>
          )}

          {/* Loading state */}
          {isLoading && conversations.length === 0 && (
            <div className="flex flex-col items-center justify-center h-64 gap-3">
              <svg
                className="animate-spin h-6 w-6 text-blue-400/40"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              <span className="text-white/55 text-xs font-mono">
                Lade Gespräche...
              </span>
            </div>
          )}

          {/* Empty state */}
          {!isLoading && conversations.length === 0 && (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
              <div className="w-16 h-16 rounded-2xl glass flex items-center justify-center">
                <svg
                  width="28"
                  height="28"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="rgba(255,255,255,0.3)"
                  strokeWidth="1.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  <path d="M8 10h.01M12 10h.01M16 10h.01" />
                </svg>
              </div>
              <div className="text-center">
                <p className="text-white/50 text-sm font-medium mb-1">
                  Keine Gespräche
                </p>
                <p className="text-white/50 text-xs font-mono">
                  Starten Sie einen Anruf, um den Verlauf zu sehen
                </p>
              </div>
            </div>
          )}

          {/* Conversation detail view */}
          {selectedConversation && (
            <ConversationDetailView
              conversation={selectedConversation}
              isLoading={isLoadingDetail}
            />
          )}

          {/* Conversation list */}
          {!selectedConversation &&
            conversations.map((conv) => (
              <ConversationCard
                key={conv.id}
                conversation={conv}
                onClick={() => loadDetail(conv.id)}
              />
            ))}
        </div>
      </div>
    </>
  );
}

/* ──────────────────────────────────── */
/*  Conversation Card                   */
/* ──────────────────────────────────── */

function ConversationCard({
  conversation,
  onClick,
}: {
  conversation: ConversationSummary;
  onClick: () => void;
}) {
  const color = PERSONA_COLORS[conversation.persona] || "#3b82f6";
  const { date, time } = formatDateTime(conversation.started_at);
  const outcomeStyle = getOutcomeStyle(conversation.outcome);

  return (
    <button
      onClick={onClick}
      className="w-full text-left glass rounded-xl p-4 hover:bg-white/[0.04] transition-all duration-200 group"
    >
      <div className="flex items-start gap-3">
        {/* Persona avatar */}
        <div
          className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center text-xs font-bold transition-all duration-200"
          style={{
            backgroundColor: `${color}18`,
            color: color,
          }}
        >
          {getPersonaInitial(conversation.persona)}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-semibold text-white/80 truncate">
              {conversation.lead_name}
            </span>
            {/* Outcome badge */}
            <span
              className="flex-shrink-0 ml-2 text-[9px] font-mono font-semibold uppercase tracking-wider rounded-full px-2 py-0.5"
              style={{
                backgroundColor: outcomeStyle.bg,
                color: outcomeStyle.text,
              }}
            >
              {conversation.outcome}
            </span>
          </div>

          {/* Meta row */}
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[10px] font-mono text-white/50">
              {getPersonaName(conversation.persona)}
            </span>
            <span className="text-white/25">|</span>
            <span className="text-[10px] font-mono text-white/50">
              {date} {time}
            </span>
            <span className="text-white/25">|</span>
            <span className="text-[10px] font-mono text-white/50">
              {conversation.message_count} Msg
            </span>
          </div>

          {/* Summary */}
          <p className="text-xs text-white/50 leading-relaxed truncate group-hover:text-white/45 transition-colors">
            {conversation.summary}
          </p>
        </div>

        {/* Expand chevron */}
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="rgba(255,255,255,0.35)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="flex-shrink-0 mt-1 group-hover:stroke-white/30 transition-colors"
        >
          <path d="M9 18l6-6-6-6" />
        </svg>
      </div>
    </button>
  );
}

/* ──────────────────────────────────── */
/*  Conversation Detail View            */
/* ──────────────────────────────────── */

function ConversationDetailView({
  conversation,
  isLoading,
}: {
  conversation: ConvDetail;
  isLoading: boolean;
}) {
  const color = PERSONA_COLORS[conversation.persona] || "#3b82f6";
  const { date, time } = formatDateTime(conversation.started_at);
  const outcomeStyle = getOutcomeStyle(conversation.outcome);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-48 gap-3">
        <svg
          className="animate-spin h-5 w-5 text-blue-400/40"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
            fill="none"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <span className="text-white/55 text-xs font-mono">
          Lade Transkript...
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Detail header card */}
      <div className="glass rounded-xl p-4">
        <div className="flex items-start gap-3 mb-3">
          {/* Persona avatar */}
          <div
            className="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold"
            style={{
              backgroundColor: `${color}18`,
              color: color,
            }}
          >
            {getPersonaInitial(conversation.persona)}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-white/90">
              {conversation.lead_name}
            </h3>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px] font-mono text-white/55">
                {getPersonaName(conversation.persona)}
              </span>
              <span className="text-white/25">|</span>
              <span className="text-[10px] font-mono text-white/55">
                {date} {time}
              </span>
            </div>
          </div>
          <span
            className="flex-shrink-0 text-[10px] font-mono font-semibold uppercase tracking-wider rounded-full px-2.5 py-1"
            style={{
              backgroundColor: outcomeStyle.bg,
              color: outcomeStyle.text,
            }}
          >
            {conversation.outcome}
          </span>
        </div>

        {/* Summary */}
        <p className="text-xs text-white/55 leading-relaxed mb-3">
          {conversation.summary}
        </p>

        {/* Metadata pills */}
        {Object.keys(conversation.lead_metadata).length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(conversation.lead_metadata).map(([key, value]) => (
              <span
                key={key}
                className="glass-input rounded-md px-2 py-0.5 text-[10px] font-mono text-white/55"
              >
                <span className="text-white/50">{key}:</span> {value}
              </span>
            ))}
          </div>
        )}

        {/* Stats row */}
        <div className="flex items-center gap-4 mt-3 pt-3 border-t border-white/[0.04]">
          <div className="flex items-center gap-1.5">
            <svg
              width="11"
              height="11"
              viewBox="0 0 24 24"
              fill="none"
              stroke="rgba(255,255,255,0.4)"
              strokeWidth="2"
            >
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span className="text-[10px] font-mono text-white/50">
              {conversation.message_count} Nachrichten
            </span>
          </div>
          {conversation.ended_at && (
            <div className="flex items-center gap-1.5">
              <svg
                width="11"
                height="11"
                viewBox="0 0 24 24"
                fill="none"
                stroke="rgba(255,255,255,0.4)"
                strokeWidth="2"
              >
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
              <span className="text-[10px] font-mono text-white/50">
                {formatDateTime(conversation.ended_at).time}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Transcript section */}
      <div>
        <h3 className="text-[11px] font-mono text-white/55 uppercase tracking-widest mb-3">
          Transkript
        </h3>
        <TranscriptView entries={conversation.transcript} />
      </div>
    </div>
  );
}
