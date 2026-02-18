import { NextRequest, NextResponse } from "next/server";
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

/** Full conversation detail returned by this endpoint (matches frontend ConversationDetail type). */
interface ConversationDetail {
  id: string;
  lead_name: string;
  persona: string;
  lead_metadata: Record<string, string>;
  transcript: StoredTranscriptItem[];
  started_at: string;
  ended_at: string;
  outcome: string;
  summary: string;
  message_count: number;
}

const CONVERSATIONS_DIR = path.resolve(
  process.cwd(),
  "..",
  "agent",
  "data",
  "conversations"
);

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  const { id } = await params;

  if (!id) {
    return NextResponse.json(
      { error: "Conversation ID is required" },
      { status: 400 }
    );
  }

  try {
    let files: string[];
    try {
      files = await fs.readdir(CONVERSATIONS_DIR);
    } catch {
      return NextResponse.json(
        { error: "Conversation not found" },
        { status: 404 }
      );
    }

    const jsonFiles = files.filter((f) => f.endsWith(".json"));

    for (const file of jsonFiles) {
      try {
        const raw = await fs.readFile(
          path.join(CONVERSATIONS_DIR, file),
          "utf-8"
        );
        const record: StoredConversationRecord = JSON.parse(raw);

        if (record.id === id) {
          const detail: ConversationDetail = {
            id: record.id,
            lead_name: record.lead_metadata?.name ?? "Unknown",
            persona: record.persona_used,
            lead_metadata: record.lead_metadata,
            transcript: record.transcript,
            started_at: record.started_at,
            ended_at: record.ended_at,
            outcome: record.outcome,
            summary: record.summary,
            message_count: record.transcript?.length ?? 0,
          };
          return NextResponse.json({ conversation: detail });
        }
      } catch {
        // Skip malformed files
        continue;
      }
    }

    return NextResponse.json(
      { error: "Conversation not found" },
      { status: 404 }
    );
  } catch (error: unknown) {
    const message =
      error instanceof Error ? error.message : "Unknown error loading conversation";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
