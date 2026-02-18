"""Main voice agent — orchestrates STT, LLM, TTS with persona routing and emotion engine."""

from __future__ import annotations

import asyncio
import json
import time

import structlog
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import cartesia, deepgram, openai, silero

from .filler_injection import FillerInjector
from .models import LeadMetadata, RequiredTone
from .persona_manager import PersonaManager
from .tonality_mapper import TonalityMapper

load_dotenv()
logger = structlog.get_logger()

# System prompt — persona addon gets injected at runtime
SYSTEM_PROMPT = """Du bist ein KI-Telefonassistent der Firma Aurus. Du führst professionelle
Verkaufsgespräche auf Deutsch.

{persona_addon}

Regeln:
- Antworte IMMER auf Deutsch
- Halte deine Antworten kurz und natürlich (1-3 Sätze)
- Sei höflich aber direkt
- Stelle Fragen um das Gespräch voranzutreiben
- Wenn der Gesprächspartner kein Interesse hat, bedanke dich höflich und beende das Gespräch"""


class AurusVoiceAgent:
    """The main Aurus voice agent with persona routing and emotion engine."""

    def __init__(self) -> None:
        self._persona_manager = PersonaManager()
        self._filler_injector = FillerInjector()
        self._tonality_mapper: TonalityMapper | None = None
        self._room: rtc.Room | None = None
        self._local_participant: rtc.LocalParticipant | None = None

    async def _publish_event(self, event_type: str, data: dict) -> None:
        """Publish an event to the room via data channel for frontend consumption."""
        if not self._local_participant:
            return
        payload = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }).encode()
        try:
            await self._local_participant.publish_data(payload, reliable=True)
        except Exception as e:
            logger.debug("event_publish_failed", error=str(e))

    async def entrypoint(self, ctx: JobContext) -> None:
        """LiveKit agent entrypoint — called when a participant joins."""
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

        self._room = ctx.room
        self._local_participant = ctx.room.local_participant

        # Extract lead metadata from room metadata or use defaults
        lead = self._extract_lead_metadata(ctx)
        persona = self._persona_manager.route(lead)
        self._tonality_mapper = TonalityMapper(persona)

        # Get default emotion settings for this persona
        default_tone = self._tonality_mapper.map_tone(RequiredTone.NEUTRAL)

        logger.info(
            "agent_starting",
            lead=lead.name,
            persona=persona.name,
            room=ctx.room.name,
            emotions=default_tone["emotions"],
        )

        # Preload fillers
        await self._filler_injector.preload()

        # Configure the agent pipeline
        system_prompt = SYSTEM_PROMPT.format(persona_addon=persona.system_prompt_addon)

        agent = Agent(
            instructions=system_prompt,
            stt=deepgram.STT(
                language="de",
                model="nova-3",
            ),
            llm=openai.LLM(
                model="gpt-4o",
                temperature=0.7,
            ),
            tts=cartesia.TTS(
                voice=persona.voice.cartesia_voice_id,
                language="de",
                speed=persona.voice.speed,
                emotion=default_tone["emotions"],
            ),
            vad=silero.VAD.load(),
            allow_interruptions=True,
            min_endpointing_delay=0.5,
        )

        session = AgentSession()
        loop = asyncio.get_event_loop()

        # Wire up event handlers for frontend broadcasting (must be sync — use create_task)
        @session.on("agent_state_changed")
        def on_agent_state_changed(event) -> None:
            new_state = event.new_state
            loop.create_task(self._publish_event("agent_state", {"state": new_state}))
            logger.debug("agent_state_changed", state=new_state)

        @session.on("user_input_transcribed")
        def on_user_input(event) -> None:
            if event.is_final:
                loop.create_task(self._publish_event("transcript", {
                    "speaker": "user",
                    "text": event.transcript,
                    "is_final": True,
                }))
                logger.info("user_speech", text=event.transcript)

        @session.on("conversation_item_added")
        def on_conversation_item(event) -> None:
            item = event.item
            if hasattr(item, "role") and item.role == "assistant":
                text_content = ""
                if hasattr(item, "content"):
                    for part in item.content:
                        if hasattr(part, "text"):
                            text_content += part.text
                if text_content:
                    loop.create_task(self._publish_event("transcript", {
                        "speaker": "agent",
                        "text": text_content,
                        "is_final": True,
                    }))

        # Listen for persona switch commands from the frontend
        @ctx.room.on("data_received")
        def on_data_received(data: rtc.DataPacket) -> None:
            try:
                msg = json.loads(data.data.decode())
                if msg.get("type") == "persona_switch":
                    new_persona_key = msg.get("persona")
                    if new_persona_key and self._tonality_mapper:
                        new_persona = self._persona_manager.get_persona(new_persona_key)
                        self._tonality_mapper.update_persona(new_persona)
                        logger.info("persona_switched_by_frontend", persona=new_persona_key)
            except (json.JSONDecodeError, KeyError):
                pass

        # Publish initial state
        await self._publish_event("agent_state", {"state": "idle"})
        await self._publish_event("persona_change", {"persona": persona.name.lower()})

        await session.start(agent=agent, room=ctx.room)

        logger.info("agent_session_started", persona=persona.name)

    def _extract_lead_metadata(self, ctx: JobContext) -> LeadMetadata:
        """Extract lead metadata from LiveKit room metadata."""
        try:
            if ctx.room.metadata:
                data = json.loads(ctx.room.metadata)
                return LeadMetadata(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("lead_metadata_parse_failed", error=str(e))

        return LeadMetadata(name="Unknown Lead")


def create_app() -> None:
    """Create and run the LiveKit agents application."""
    agent = AurusVoiceAgent()
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=agent.entrypoint,
            agent_name="aurus-voice-agent",
        )
    )


if __name__ == "__main__":
    create_app()
