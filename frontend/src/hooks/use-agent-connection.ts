"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  Room,
  RoomEvent,
  Track,
  RemoteTrack,
  RemoteTrackPublication,
  RemoteParticipant,
  ConnectionState,
} from "livekit-client";
import type {
  AgentState,
  CallMetricsData,
  CallSummaryData,
  MoodDataPoint,
  TranscriptEntry,
  UserMood,
  RequiredTone,
} from "@/lib/types";

const LIVEKIT_URL = process.env.NEXT_PUBLIC_LIVEKIT_URL || "";

interface AgentConnectionState {
  connectionState: ConnectionState | "disconnected";
  agentState: AgentState;
  activePersona: string;
  moodHistory: MoodDataPoint[];
  transcript: TranscriptEntry[];
  agentAudioTrack: MediaStreamTrack | null;
  callMetrics: CallMetricsData | null;
  callStartTime: number | null;
  callSummary: CallSummaryData | null;
  connect: (roomName: string, participantName: string, metadata?: Record<string, string>) => Promise<void>;
  disconnect: () => void;
  sendPersonaSwitch: (personaKey: string) => void;
  dismissSummary: () => void;
}

export function useAgentConnection(): AgentConnectionState {
  const roomRef = useRef<Room | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState | "disconnected">("disconnected");
  const [agentState, setAgentState] = useState<AgentState>("idle");
  const [activePersona, setActivePersona] = useState("lukas");
  const [moodHistory, setMoodHistory] = useState<MoodDataPoint[]>([]);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [agentAudioTrack, setAgentAudioTrack] = useState<MediaStreamTrack | null>(null);
  const [callMetrics, setCallMetrics] = useState<CallMetricsData | null>(null);
  const [callStartTime, setCallStartTime] = useState<number | null>(null);
  const [callSummary, setCallSummary] = useState<CallSummaryData | null>(null);

  const handleDataReceived = useCallback(
    (payload: Uint8Array, participant?: RemoteParticipant) => {
      try {
        const text = new TextDecoder().decode(payload);
        const event = JSON.parse(text);

        switch (event.type) {
          case "agent_state":
            setAgentState(event.data.state as AgentState);
            break;

          case "mood_update":
            setMoodHistory((prev) => [
              ...prev,
              {
                timestamp: Date.now() / 1000,
                mood: event.data.mood as UserMood,
                tone: event.data.tone as RequiredTone,
              },
            ]);
            break;

          case "persona_change":
            setActivePersona(event.data.persona);
            break;

          case "transcript":
            setTranscript((prev) => [
              ...prev,
              {
                speaker: event.data.speaker,
                text: event.data.text,
                timestamp: Date.now() / 1000,
                mood: event.data.mood,
              },
            ]);
            break;

          case "call_metrics":
            setCallMetrics(event.data as CallMetricsData);
            break;

          case "call_summary":
            setCallSummary(event.data as CallSummaryData);
            break;
        }
      } catch {
        // Non-JSON data, ignore
      }
    },
    []
  );

  const handleTrackSubscribed = useCallback(
    (
      track: RemoteTrack,
      publication: RemoteTrackPublication,
      participant: RemoteParticipant
    ) => {
      if (track.kind === Track.Kind.Audio) {
        const stream = new MediaStream([track.mediaStreamTrack]);
        // Attach audio for playback
        const audioEl = document.createElement("audio");
        audioEl.srcObject = stream;
        audioEl.autoplay = true;
        audioEl.id = `agent-audio-${participant.identity}`;
        document.body.appendChild(audioEl);

        setAgentAudioTrack(track.mediaStreamTrack);
        setAgentState("speaking");
      }
    },
    []
  );

  const handleTrackUnsubscribed = useCallback(
    (track: RemoteTrack, publication: RemoteTrackPublication, participant: RemoteParticipant) => {
      if (track.kind === Track.Kind.Audio) {
        const audioEl = document.getElementById(`agent-audio-${participant.identity}`);
        audioEl?.remove();
        setAgentAudioTrack(null);
      }
    },
    []
  );

  const connect = useCallback(
    async (roomName: string, participantName: string, metadata?: Record<string, string>) => {
      // Get token from API
      const res = await fetch("/api/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ roomName, participantName, metadata }),
      });

      if (!res.ok) {
        throw new Error(`Token request failed: ${res.statusText}`);
      }

      const { token } = await res.json();

      // Create and connect room
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });

      room.on(RoomEvent.DataReceived, handleDataReceived);
      room.on(RoomEvent.TrackSubscribed, handleTrackSubscribed);
      room.on(RoomEvent.TrackUnsubscribed, handleTrackUnsubscribed);
      room.on(RoomEvent.ConnectionStateChanged, (state) => {
        setConnectionState(state);
      });
      room.on(RoomEvent.Disconnected, () => {
        setConnectionState("disconnected");
        setAgentState("idle");
        setAgentAudioTrack(null);
      });

      // LiveKit agents SDK sends transcription events
      room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        for (const segment of segments) {
          if (segment.final) {
            const isAgent = participant?.identity?.includes("agent");
            setTranscript((prev) => [
              ...prev,
              {
                speaker: isAgent ? "agent" : "user",
                text: segment.text,
                timestamp: Date.now() / 1000,
              },
            ]);
          }
        }
      });

      await room.connect(LIVEKIT_URL, token);

      // Enable microphone
      await room.localParticipant.setMicrophoneEnabled(true);

      roomRef.current = room;
      setConnectionState(ConnectionState.Connected);
      setCallStartTime(Date.now() / 1000);
    },
    [handleDataReceived, handleTrackSubscribed, handleTrackUnsubscribed]
  );

  const disconnect = useCallback(() => {
    roomRef.current?.disconnect();
    roomRef.current = null;
    setConnectionState("disconnected");
    setAgentState("idle");
    setMoodHistory([]);
    setTranscript([]);
    setAgentAudioTrack(null);
    setCallMetrics(null);
    setCallStartTime(null);
    // Don't clear summary on disconnect — user should see it
  }, []);

  const dismissSummary = useCallback(() => {
    setCallSummary(null);
  }, []);

  const sendPersonaSwitch = useCallback((personaKey: string) => {
    if (!roomRef.current) return;
    const data = new TextEncoder().encode(
      JSON.stringify({ type: "persona_switch", persona: personaKey })
    );
    roomRef.current.localParticipant.publishData(data, { reliable: true });
    setActivePersona(personaKey);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      roomRef.current?.disconnect();
    };
  }, []);

  return {
    connectionState,
    agentState,
    activePersona,
    moodHistory,
    transcript,
    agentAudioTrack,
    callMetrics,
    callStartTime,
    callSummary,
    connect,
    disconnect,
    sendPersonaSwitch,
    dismissSummary,
  };
}
