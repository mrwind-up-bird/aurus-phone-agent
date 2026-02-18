import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

/** Shape of a single transcript item in the stored JSON. */
interface StoredTranscriptItem {
  speaker: string;
  text: string;
  timestamp: number;
  mood: string;
}

/** Shape of the full conversation record stored on disk. */
interface StoredConversationRecord {
  id: string;
  lead_metadata: Record<string, string>;
  persona_used: string;
  transcript: StoredTranscriptItem[];
  started_at: string;
  ended_at: string;
  outcome: string;
  summary: string;
}

/** Summarized conversation returned by the list endpoint. */
interface ConversationSummary {
  id: string;
  lead_name: string;
  persona: string;
  started_at: string;
  outcome: string;
  message_count: number;
  summary: string;
}

const CONVERSATIONS_DIR = path.resolve(
  process.cwd(),
  "..",
  "agent",
  "data",
  "conversations"
);

export async function GET(): Promise<NextResponse> {
  try {
    let files: string[];
    try {
      files = await fs.readdir(CONVERSATIONS_DIR);
    } catch {
      // Directory doesn't exist yet — return empty list
      return NextResponse.json({ conversations: [] });
    }

    const jsonFiles = files
      .filter((f) => f.endsWith(".json"))
      .sort()
      .reverse(); // newest first (files are timestamped)

    const conversations: ConversationSummary[] = [];

    for (const file of jsonFiles) {
      try {
        const raw = await fs.readFile(
          path.join(CONVERSATIONS_DIR, file),
          "utf-8"
        );
        const record: StoredConversationRecord = JSON.parse(raw);

        conversations.push({
          id: record.id,
          lead_name: record.lead_metadata?.name ?? "Unknown",
          persona: record.persona_used,
          started_at: record.started_at,
          outcome: record.outcome,
          message_count: record.transcript?.length ?? 0,
          summary: record.summary,
        });
      } catch {
        // Skip malformed files silently
        continue;
      }
    }

    return NextResponse.json({ conversations });
  } catch (error: unknown) {
    const message =
      error instanceof Error ? error.message : "Unknown error reading conversations";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
