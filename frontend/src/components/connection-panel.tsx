"use client";

import { useState } from "react";
import { ConnectionState } from "livekit-client";

interface ConnectionPanelProps {
  connectionState: ConnectionState | "disconnected";
  onConnect: (
    roomName: string,
    participantName: string,
    metadata?: Record<string, string>
  ) => Promise<void>;
  onDisconnect: () => void;
}

const DEMO_PRESETS = [
  {
    label: "CEO",
    name: "Thomas Weber",
    company: "AutoVision AG",
    title: "Geschäftsführer",
    gender: "Male",
    color: "#3b82f6",
    persona: "Lukas",
  },
  {
    label: "HR",
    name: "Lisa Schmidt",
    company: "CloudFirst GmbH",
    title: "Head of People",
    gender: "Female",
    color: "#ec4899",
    persona: "Sarah",
  },
  {
    label: "CTO",
    name: "Max Müller",
    company: "TechVision GmbH",
    title: "CTO",
    gender: "Male",
    color: "#22c55e",
    persona: "Marcus",
  },
];

export function ConnectionPanel({
  connectionState,
  onConnect,
  onDisconnect,
}: ConnectionPanelProps) {
  const [roomName, setRoomName] = useState("aurus-demo");
  const [leadName, setLeadName] = useState("Max Müller");
  const [leadCompany, setLeadCompany] = useState("TechVision GmbH");
  const [leadTitle, setLeadTitle] = useState("CTO");
  const [leadGender, setLeadGender] = useState("Male");
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isConnected = connectionState === ConnectionState.Connected;

  const applyPreset = (preset: typeof DEMO_PRESETS[0]) => {
    setLeadName(preset.name);
    setLeadCompany(preset.company);
    setLeadTitle(preset.title);
    setLeadGender(preset.gender);
    setError(null);
  };

  const handleConnect = async () => {
    setIsConnecting(true);
    setError(null);
    try {
      await onConnect(roomName, `dashboard-${Date.now()}`, {
        name: leadName,
        company: leadCompany,
        job_title: leadTitle,
        gender: leadGender,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verbindung fehlgeschlagen");
      console.error("Connection failed:", err);
    } finally {
      setIsConnecting(false);
    }
  };

  if (isConnected) {
    return (
      <div className="glass rounded-2xl px-5 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
            <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-green-500 animate-ping opacity-40" />
          </div>
          <div>
            <span className="text-sm text-white/80 font-medium">
              {leadName}
            </span>
            <span className="text-white/20 mx-1.5">&middot;</span>
            <span className="text-xs text-white/40 font-mono">{leadTitle}</span>
            {leadCompany && (
              <>
                <span className="text-white/20 mx-1.5">&middot;</span>
                <span className="text-xs text-white/30 font-mono">{leadCompany}</span>
              </>
            )}
          </div>
        </div>
        <button
          onClick={onDisconnect}
          className="glass-input rounded-lg px-4 py-1.5 text-xs font-mono text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-all duration-200"
        >
          Auflegen
        </button>
      </div>
    );
  }

  return (
    <div className="glass rounded-2xl p-5">
      {/* Demo scenario presets */}
      <div className="flex items-center gap-2 mb-4">
        <span className="text-[10px] font-mono text-white/20 uppercase tracking-wider mr-1">
          Szenarien
        </span>
        {DEMO_PRESETS.map((preset) => (
          <button
            key={preset.label}
            onClick={() => applyPreset(preset)}
            className="glass-input rounded-lg px-3 py-1.5 text-[10px] font-mono transition-all duration-200 hover:bg-white/5 flex items-center gap-1.5"
            style={{ color: `${preset.color}cc` }}
          >
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: preset.color }}
            />
            {preset.label}
            <span className="text-white/20">&rarr;</span>
            <span className="text-white/30">{preset.persona}</span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
        <div>
          <label className="text-[10px] font-mono text-white/25 uppercase tracking-wider block mb-1.5">
            Raum
          </label>
          <input
            type="text"
            value={roomName}
            onChange={(e) => setRoomName(e.target.value)}
            className="w-full glass-input rounded-lg px-3 py-2 text-sm text-white/80 placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-blue-500/30 transition"
          />
        </div>
        <div>
          <label className="text-[10px] font-mono text-white/25 uppercase tracking-wider block mb-1.5">
            Lead Name
          </label>
          <input
            type="text"
            value={leadName}
            onChange={(e) => setLeadName(e.target.value)}
            className="w-full glass-input rounded-lg px-3 py-2 text-sm text-white/80 placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-blue-500/30 transition"
          />
        </div>
        <div>
          <label className="text-[10px] font-mono text-white/25 uppercase tracking-wider block mb-1.5">
            Unternehmen
          </label>
          <input
            type="text"
            value={leadCompany}
            onChange={(e) => setLeadCompany(e.target.value)}
            placeholder="z.B. TechVision GmbH"
            className="w-full glass-input rounded-lg px-3 py-2 text-sm text-white/80 placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-blue-500/30 transition"
          />
        </div>
        <div>
          <label className="text-[10px] font-mono text-white/25 uppercase tracking-wider block mb-1.5">
            Position
          </label>
          <input
            type="text"
            value={leadTitle}
            onChange={(e) => setLeadTitle(e.target.value)}
            className="w-full glass-input rounded-lg px-3 py-2 text-sm text-white/80 placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-blue-500/30 transition"
          />
        </div>
        <div>
          <label className="text-[10px] font-mono text-white/25 uppercase tracking-wider block mb-1.5">
            Geschlecht
          </label>
          <select
            value={leadGender}
            onChange={(e) => setLeadGender(e.target.value)}
            className="w-full glass-input rounded-lg px-3 py-2 text-sm text-white/80 focus:outline-none focus:ring-1 focus:ring-blue-500/30 transition appearance-none"
          >
            <option value="Male">Herr</option>
            <option value="Female">Frau</option>
          </select>
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="mb-3 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400 font-mono">
          {error}
        </div>
      )}

      <button
        onClick={handleConnect}
        disabled={isConnecting}
        className="w-full rounded-xl py-2.5 text-sm font-semibold transition-all duration-300 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isConnecting ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Verbinde...
          </span>
        ) : (
          "Anruf starten"
        )}
      </button>
    </div>
  );
}
