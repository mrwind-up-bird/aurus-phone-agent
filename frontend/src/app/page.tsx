"use client";

import { useState, useCallback, useEffect } from "react";
import { AudioVisualizer } from "@/components/audio-visualizer";
import { SentimentGraph } from "@/components/sentiment-graph";
import { SentimentCoaching } from "@/components/sentiment-coaching";
import { AgentStateIndicator } from "@/components/agent-state-indicator";
import { PersonaSwitcher } from "@/components/persona-switcher";
import { TranscriptView } from "@/components/transcript-view";
import { ConnectionPanel } from "@/components/connection-panel";
import { ConversationHistory } from "@/components/conversation-history";
import { CallMetrics } from "@/components/call-metrics";
import { CallSummaryOverlay } from "@/components/call-summary-overlay";
import { useAgentConnection } from "@/hooks/use-agent-connection";
import type {
  AgentState,
  MoodDataPoint,
  RequiredTone,
  TranscriptEntry,
} from "@/lib/types";

const DEMO_MOODS: MoodDataPoint[] = [
  { timestamp: 0, mood: "neutral", tone: "professional" },
  { timestamp: 3, mood: "skeptical", tone: "reassuring" },
  { timestamp: 7, mood: "interested", tone: "enthusiastic" },
  { timestamp: 12, mood: "enthusiastic", tone: "enthusiastic" },
  { timestamp: 16, mood: "interested", tone: "professional" },
];

const DEMO_TRANSCRIPT: TranscriptEntry[] = [
  {
    speaker: "agent",
    text: "Guten Tag, Herr Müller. Hier ist Sarah von Aurus. Haben Sie kurz Zeit?",
    timestamp: 0,
  },
  {
    speaker: "user",
    text: "Ja, worum geht es denn?",
    timestamp: 3,
    mood: "skeptical",
  },
  {
    speaker: "agent",
    text: "Das ist absolut verständlich. Ich möchte Ihnen kurz zeigen, wie wir Ihre Vertriebseffizienz verdoppeln können.",
    timestamp: 5,
  },
  {
    speaker: "user",
    text: "Klingt interessant. Erzählen Sie mehr.",
    timestamp: 9,
    mood: "interested",
  },
  {
    speaker: "agent",
    text: "Genau! Unsere KI-Lösung automatisiert die Erstansprache und qualifiziert Leads in Echtzeit.",
    timestamp: 11,
  },
];

export default function Dashboard() {
  const connection = useAgentConnection();
  const isLive = connection.connectionState === "connected";

  const [demoState, setDemoState] = useState<AgentState>("idle");
  const [historyOpen, setHistoryOpen] = useState(false);

  const agentState = isLive ? connection.agentState : demoState;
  const moodData = isLive ? connection.moodHistory : DEMO_MOODS;
  const transcript = isLive ? connection.transcript : DEMO_TRANSCRIPT;
  const activePersona = connection.activePersona;
  const audioTrack = isLive ? connection.agentAudioTrack : null;

  const cycleState = useCallback(() => {
    const states: AgentState[] = [
      "idle",
      "listening",
      "thinking",
      "filler",
      "speaking",
    ];
    setDemoState((prev) => {
      const idx = states.indexOf(prev);
      return states[(idx + 1) % states.length];
    });
  }, []);

  const handlePersonaSwitch = useCallback(
    (key: string) => {
      connection.sendPersonaSwitch(key);
    },
    [connection]
  );

  const handleToneShift = useCallback(
    (tone: RequiredTone) => {
      connection.sendToneShift(tone);
    },
    [connection]
  );

  // Keyboard shortcuts for quick operator actions
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;

      switch (e.key) {
        case "1":
          connection.sendPersonaSwitch("lukas");
          break;
        case "2":
          connection.sendPersonaSwitch("sarah");
          break;
        case "3":
          connection.sendPersonaSwitch("marcus");
          break;
        case "h":
          setHistoryOpen((prev) => !prev);
          break;
        case "t": {
          const toneSection = document.querySelector("[data-tone-shift]");
          if (toneSection) toneSection.scrollIntoView({ behavior: "smooth", block: "center" });
          break;
        }
        case "Escape":
          setHistoryOpen(false);
          connection.dismissSummary();
          break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [connection]);

  return (
    <div className="ambient-bg min-h-screen text-white/90">
      <div className="relative z-10 max-w-[1440px] mx-auto px-6 py-6">
        {/* Header */}
        <header className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            {/* Logo */}
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <span className="text-white font-bold text-sm">A</span>
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">
                Aurus
                <span className="text-blue-400 ml-1.5">Voice</span>
              </h1>
              <p className="text-[10px] font-mono text-white/25 uppercase tracking-widest">
                Team Everlast
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* History toggle */}
            <button
              onClick={() => setHistoryOpen(true)}
              className="glass rounded-full px-3.5 py-1.5 flex items-center gap-2 hover:bg-white/5 transition-all duration-200"
              title="Gesprächsverlauf"
            >
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="rgba(255,255,255,0.4)"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <span className="text-[10px] font-mono text-white/40 uppercase tracking-wider">
                History
              </span>
            </button>

            {/* Mode badge */}
            {!isLive ? (
              <button
                onClick={cycleState}
                className="glass rounded-full px-3.5 py-1.5 text-[10px] font-mono text-amber-400/80 uppercase tracking-wider hover:bg-white/5 transition"
              >
                Demo
              </button>
            ) : (
              <div className="glass rounded-full px-3.5 py-1.5 flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                <span className="text-[10px] font-mono text-green-400/80 uppercase tracking-wider">
                  Live
                </span>
              </div>
            )}
            <AgentStateIndicator state={agentState} />
          </div>
        </header>

        {/* Connection */}
        <div className="mb-6">
          <ConnectionPanel
            connectionState={connection.connectionState}
            onConnect={connection.connect}
            onDisconnect={connection.disconnect}
          />
        </div>

        {/* Call Metrics Bar */}
        <div className="mb-5">
          <CallMetrics
            isLive={isLive}
            metrics={connection.callMetrics}
            callStartTime={connection.callStartTime}
          />
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Left: Visualizer + Sentiment + Personas */}
          <div className="lg:col-span-8 space-y-5">
            {/* Audio Visualizer */}
            <section className="glass rounded-2xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-[11px] font-mono text-white/30 uppercase tracking-widest">
                  Audio Stream
                </h2>
                {/* Pipeline indicator — lights up based on agent state */}
                <div className="flex items-center gap-0.5">
                  {(["STT", "LLM", "TTS"] as const).map((step, i) => {
                    const activeStep =
                      agentState === "listening" ? "STT" :
                      agentState === "thinking" ? "LLM" :
                      agentState === "speaking" ? "TTS" :
                      agentState === "filler" ? "TTS" : null;
                    const isActive = activeStep === step;
                    const stepColor =
                      step === "STT" ? "#3b82f6" :
                      step === "LLM" ? "#f59e0b" : "#22c55e";
                    return (
                      <span key={step} className="flex items-center">
                        <span
                          className="text-[9px] font-mono px-1.5 py-0.5 rounded transition-all duration-300"
                          style={{
                            color: isActive ? stepColor : "rgba(255,255,255,0.2)",
                            background: isActive ? `${stepColor}15` : "rgba(255,255,255,0.03)",
                            boxShadow: isActive ? `0 0 8px ${stepColor}30` : "none",
                          }}
                        >
                          {step}
                        </span>
                        {i < 2 && (
                          <svg
                            width="12"
                            height="8"
                            viewBox="0 0 12 8"
                            className="mx-0.5 transition-colors duration-300"
                            style={{
                              color: isActive ? stepColor : "rgba(255,255,255,0.1)",
                            }}
                          >
                            <path
                              d="M0 4h8m0 0L6 2m2 2L6 6"
                              stroke="currentColor"
                              strokeWidth="1"
                              fill="none"
                            />
                          </svg>
                        )}
                      </span>
                    );
                  })}
                </div>
              </div>
              <AudioVisualizer state={agentState} audioTrack={audioTrack} />
            </section>

            {/* Sentiment Analysis */}
            <section className="glass rounded-2xl p-5">
              <h2 className="text-[11px] font-mono text-white/30 uppercase tracking-widest mb-3">
                Stimmungsanalyse
              </h2>
              <SentimentGraph data={moodData} />
            </section>

            {/* Coaching & Tone Control */}
            <SentimentCoaching
              moodHistory={moodData}
              activeTone={connection.activeTone}
              onToneShift={handleToneShift}
              isLive={isLive}
            />

            {/* Persona Override */}
            <section className="glass rounded-2xl p-5">
              <h2 className="text-[11px] font-mono text-white/30 uppercase tracking-widest mb-4">
                Persona
              </h2>
              <PersonaSwitcher
                activePersona={activePersona}
                onSwitch={handlePersonaSwitch}
              />
            </section>
          </div>

          {/* Right: Transcript */}
          <div className="lg:col-span-4">
            <section className="glass rounded-2xl p-5 lg:sticky lg:top-6">
              <h2 className="text-[11px] font-mono text-white/30 uppercase tracking-widest mb-4">
                Transkript
              </h2>
              <TranscriptView entries={transcript} />
            </section>
          </div>
        </div>

        {/* Keyboard shortcuts hint */}
        <div className="mt-6 flex items-center justify-center gap-4 text-[9px] font-mono text-white/15">
          {[
            ["1", "Lukas"],
            ["2", "Sarah"],
            ["3", "Marcus"],
            ["T", "Ton"],
            ["H", "History"],
            ["Esc", "Schließen"],
          ].map(([key, label]) => (
            <span key={key} className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 rounded border border-white/10 bg-white/5 text-white/25">
                {key}
              </kbd>
              <span>{label}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Conversation History Panel */}
      <ConversationHistory
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />

      {/* Post-Call Summary Overlay */}
      {connection.callSummary && (
        <CallSummaryOverlay
          summary={connection.callSummary}
          onDismiss={connection.dismissSummary}
        />
      )}
    </div>
  );
}
