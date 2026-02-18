export type AgentState = "initializing" | "idle" | "listening" | "thinking" | "speaking" | "filler";

export type UserMood =
  | "neutral"
  | "interested"
  | "skeptical"
  | "frustrated"
  | "enthusiastic"
  | "confused"
  | "dismissive";

export type RequiredTone =
  | "neutral"
  | "reassuring"
  | "enthusiastic"
  | "empathetic"
  | "professional"
  | "urgent";

export interface MoodDataPoint {
  timestamp: number;
  mood: UserMood;
  tone: RequiredTone;
}

export interface Persona {
  key: string;
  name: string;
  role: string;
  description: string;
}

export interface TranscriptEntry {
  speaker: "user" | "agent";
  text: string;
  timestamp: number;
  mood?: UserMood;
}

export const PERSONAS: Persona[] = [
  {
    key: "lukas",
    name: "Lukas",
    role: "The Closer",
    description: "Professional, calm, authoritative",
  },
  {
    key: "sarah",
    name: "Sarah",
    role: "The Empath",
    description: "Warm, enthusiastic, empathetic",
  },
  {
    key: "marcus",
    name: "Marcus",
    role: "The Techie",
    description: "Fast, direct, technical",
  },
];

export const MOOD_COLORS: Record<UserMood, string> = {
  neutral: "#94a3b8",
  interested: "#22c55e",
  skeptical: "#f59e0b",
  frustrated: "#ef4444",
  enthusiastic: "#3b82f6",
  confused: "#a855f7",
  dismissive: "#6b7280",
};

export const STATE_CONFIG: Record<
  AgentState,
  { label: string; color: string; pulse: boolean }
> = {
  initializing: { label: "Initialisiert", color: "#6b7280", pulse: true },
  idle: { label: "Bereit", color: "#6b7280", pulse: false },
  listening: { label: "Hört zu", color: "#3b82f6", pulse: true },
  thinking: { label: "Denkt nach", color: "#f59e0b", pulse: true },
  speaking: { label: "Spricht", color: "#22c55e", pulse: true },
  filler: { label: "Filler", color: "#8b5cf6", pulse: true },
};

export interface ConversationSummary {
  id: string;
  lead_name: string;
  persona: string;
  started_at: string;
  outcome: string;
  message_count: number;
  summary: string;
}

export interface ConversationDetail extends ConversationSummary {
  lead_metadata: Record<string, string>;
  transcript: TranscriptEntry[];
  ended_at: string;
}

export interface CallSummaryData {
  outcome: string;
  summary: string;
  lead_score: number;
  turn_count: number;
  duration_seconds: number;
  mood_trajectory: string;
}

export interface CallMetricsData {
  duration_seconds: number;
  turn_count: number;
  user_turns: number;
  agent_turns: number;
  lead_score: number;
  current_stage: string;
  objection_count: number;
  avg_response_time_ms: number;
  mood_trajectory: string;
}
