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

  const isConnected = connectionState === ConnectionState.Connected;

  const handleConnect = async () => {
    setIsConnecting(true);
    try {
      await onConnect(roomName, `dashboard-${Date.now()}`, {
        name: leadName,
        company: leadCompany,
        job_title: leadTitle,
        gender: leadGender,
      });
    } catch (err) {
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
            <span className="text-white/20 mx-1.5">·</span>
            <span className="text-xs text-white/40 font-mono">{leadTitle}</span>
            {leadCompany && (
              <>
                <span className="text-white/20 mx-1.5">·</span>
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
