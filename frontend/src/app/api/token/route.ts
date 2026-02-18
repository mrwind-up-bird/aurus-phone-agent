import { NextRequest, NextResponse } from "next/server";
import {
  AccessToken,
  AgentDispatchClient,
  RoomServiceClient,
} from "livekit-server-sdk";

const LK_URL = process.env.NEXT_PUBLIC_LIVEKIT_URL || "";
const LK_HOST = LK_URL.replace("wss://", "https://");

export async function POST(req: NextRequest) {
  const { roomName, participantName, metadata } = await req.json();

  if (!roomName || !participantName) {
    return NextResponse.json(
      { error: "roomName and participantName are required" },
      { status: 400 }
    );
  }

  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;

  if (!apiKey || !apiSecret) {
    return NextResponse.json(
      { error: "LiveKit credentials not configured" },
      { status: 500 }
    );
  }

  // 1. Create room with lead metadata so the agent can read it
  const roomService = new RoomServiceClient(LK_HOST, apiKey, apiSecret);
  try {
    await roomService.createRoom({
      name: roomName,
      metadata: metadata ? JSON.stringify(metadata) : "",
    });
  } catch {
    // Room may already exist — that's fine
  }

  // 2. Dispatch the agent to this room
  const dispatchClient = new AgentDispatchClient(LK_HOST, apiKey, apiSecret);
  try {
    await dispatchClient.createDispatch(roomName, "aurus-voice-agent", {
      metadata: metadata ? JSON.stringify(metadata) : undefined,
    });
  } catch (e) {
    console.error("Agent dispatch failed:", e);
  }

  // 3. Generate participant token
  const token = new AccessToken(apiKey, apiSecret, {
    identity: participantName,
    metadata: metadata ? JSON.stringify(metadata) : undefined,
  });

  token.addGrant({
    roomJoin: true,
    room: roomName,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  });

  const jwt = await token.toJwt();

  return NextResponse.json({ token: jwt });
}
