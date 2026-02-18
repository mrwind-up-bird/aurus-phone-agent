"""Main voice agent — orchestrates STT, LLM, TTS with persona routing and emotion engine."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

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

from .conversation_store import ConversationRecord, ConversationStore, TranscriptItem
from .filler_injection import FillerInjector
from .models import LeadMetadata, RequiredTone, UserMood
from .persona_manager import PersonaManager
from .tonality_mapper import TonalityMapper

# German keyword patterns for mood detection (lowercase)
_MOOD_KEYWORDS: dict[UserMood, list[str]] = {
    UserMood.ENTHUSIASTIC: [
        "super", "toll", "großartig", "perfekt", "genial", "fantastisch", "wunderbar",
        "ausgezeichnet", "klasse", "mega", "spitze", "ja gerne", "auf jeden fall",
        "unbedingt", "begeistert", "freue mich",
    ],
    UserMood.INTERESTED: [
        "interessant", "erzählen sie", "mehr dazu", "wie funktioniert", "klingt gut",
        "spannend", "neugierig", "gerne mehr", "wie genau", "was genau", "können sie",
        "zeigen sie", "erklären", "details",
    ],
    UserMood.SKEPTICAL: [
        "weiß nicht", "bin mir nicht sicher", "eher nicht", "glaube nicht", "skeptisch",
        "überzeugt", "nicht überzeugt", "woher wissen", "beweis", "nachweis",
        "garantie", "hm naja", "mal sehen", "vielleicht",
    ],
    UserMood.FRUSTRATED: [
        "nervig", "schon wieder", "keine zeit", "aufhören", "lassen sie mich",
        "ruhe", "genervt", "ärgerlich", "schlecht", "unverschämt", "frechheit",
        "beschwerde", "problem", "funktioniert nicht",
    ],
    UserMood.CONFUSED: [
        "verstehe nicht", "was meinen sie", "wie bitte", "unklar", "verwirrt",
        "nochmal", "wiederholen", "häh", "ich folge nicht", "zu schnell",
        "langsamer", "kompliziert",
    ],
    UserMood.DISMISSIVE: [
        "kein interesse", "nein danke", "brauche ich nicht", "auf wiedersehen",
        "auflegen", "tschüss", "nicht interessiert", "lassen sie es", "vergessen sie es",
        "zeitverschwendung", "rufen sie nicht",
    ],
}

# Map detected mood to the optimal agent response tone
_MOOD_TO_TONE: dict[UserMood, RequiredTone] = {
    UserMood.NEUTRAL: RequiredTone.PROFESSIONAL,
    UserMood.INTERESTED: RequiredTone.ENTHUSIASTIC,
    UserMood.ENTHUSIASTIC: RequiredTone.ENTHUSIASTIC,
    UserMood.SKEPTICAL: RequiredTone.REASSURING,
    UserMood.FRUSTRATED: RequiredTone.EMPATHETIC,
    UserMood.CONFUSED: RequiredTone.REASSURING,
    UserMood.DISMISSIVE: RequiredTone.EMPATHETIC,
}

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
        self._session: AgentSession | None = None
        self._conversation_store = ConversationStore()
        self._transcript: list[TranscriptItem] = []
        self._lead: LeadMetadata | None = None
        self._persona_name: str = ""
        self._started_at: str = ""
        self._outcome: str = "end_call"
        self._current_mood: UserMood = UserMood.NEUTRAL
        self._current_tone: RequiredTone = RequiredTone.PROFESSIONAL
        self._current_persona_key: str = "lukas"

    @staticmethod
    def _detect_mood(text: str) -> UserMood:
        """Detect user mood from German text using keyword matching."""
        lower = text.lower()
        best_mood = UserMood.NEUTRAL
        best_score = 0
        for mood, keywords in _MOOD_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in lower)
            if score > best_score:
                best_score = score
                best_mood = mood
        return best_mood

    async def _update_emotion(self, mood: UserMood) -> None:
        """Update TTS emotions based on detected user mood."""
        if not self._tonality_mapper or not self._session:
            return

        tone = _MOOD_TO_TONE.get(mood, RequiredTone.PROFESSIONAL)

        # Only update agent if tone actually changed
        if tone == self._current_tone:
            return

        self._current_tone = tone
        mapped = self._tonality_mapper.map_tone(tone)
        persona = self._persona_manager.get_persona(self._current_persona_key)

        new_agent = Agent(
            instructions=SYSTEM_PROMPT.format(persona_addon=persona.system_prompt_addon),
            stt=deepgram.STT(language="de", model="nova-3"),
            llm=openai.LLM(model="gpt-4o", temperature=0.7),
            tts=cartesia.TTS(
                voice=mapped["voice_id"],
                language="de",
                speed=mapped["speed"],
                emotion=mapped["emotions"],
            ),
            vad=silero.VAD.load(),
            allow_interruptions=True,
            min_endpointing_delay=0.5,
        )

        self._session.update_agent(new_agent)
        logger.info("emotion_updated", mood=mood.value, tone=tone.value, emotions=mapped["emotions"])

    def _record_transcript(self, speaker: str, text: str, mood: str = "neutral") -> None:
        """Append a transcript entry to the in-memory log."""
        self._transcript.append(
            TranscriptItem(
                speaker=speaker,
                text=text,
                timestamp=time.time(),
                mood=mood,
            )
        )

    async def _handle_persona_switch(self, new_persona_key: str) -> None:
        """Hot-swap the agent persona during a live call.

        Steps:
        1. Load the new persona from PersonaManager
        2. Update the TonalityMapper
        3. Build a new Agent with updated TTS settings and system prompt
        4. Call session.update_agent() to hot-swap the running agent
        5. Publish a persona_change event to the frontend
        """
        try:
            new_persona = self._persona_manager.get_persona(new_persona_key)
        except KeyError:
            logger.warning("persona_switch_failed_unknown_key", key=new_persona_key)
            return

        # 1. Update tonality mapper to the new persona
        self._tonality_mapper.update_persona(new_persona)

        # 2. Get default emotions for the new persona
        default_tone = self._tonality_mapper.map_tone(RequiredTone.NEUTRAL)

        # 3. Build the new system prompt with updated persona addon
        system_prompt = SYSTEM_PROMPT.format(persona_addon=new_persona.system_prompt_addon)

        # 4. Create a new Agent with the new persona's voice and instructions
        new_agent = Agent(
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
                voice=new_persona.voice.cartesia_voice_id,
                language="de",
                speed=new_persona.voice.speed,
                emotion=default_tone["emotions"],
            ),
            vad=silero.VAD.load(),
            allow_interruptions=True,
            min_endpointing_delay=0.5,
        )

        # 5. Hot-swap the agent (synchronous call — internally creates async task)
        self._session.update_agent(new_agent)

        # 6. Update internal state
        self._persona_name = new_persona.name
        self._current_persona_key = new_persona_key
        self._current_tone = RequiredTone.NEUTRAL  # Reset tone on persona switch

        # 7. Notify the frontend
        await self._publish_event("persona_change", {
            "persona": new_persona_key,
            "persona_name": new_persona.name,
        })

        logger.info(
            "persona_switched",
            new_persona=new_persona_key,
            voice_id=new_persona.voice.cartesia_voice_id,
            speed=new_persona.voice.speed,
            emotions=default_tone["emotions"],
        )

    async def _save_conversation(self) -> None:
        """Persist the current conversation to disk."""
        lead_meta = (
            self._lead.model_dump() if self._lead else {"name": "Unknown Lead"}
        )
        # Convert any non-string values for JSON compatibility
        lead_meta_str = {k: str(v) for k, v in lead_meta.items()}

        record = ConversationRecord(
            lead_metadata=lead_meta_str,
            persona_used=self._persona_name,
            transcript=list(self._transcript),
            started_at=self._started_at,
            ended_at=datetime.now(tz=timezone.utc).isoformat(),
            outcome=self._outcome,
        )
        try:
            filepath = await self._conversation_store.save(record)
            logger.info("conversation_persisted", path=str(filepath), turns=len(self._transcript))
        except Exception as exc:
            logger.error("conversation_save_failed", error=str(exc))

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

        # Store references for conversation persistence and emotion engine
        self._lead = lead
        self._persona_name = persona.name
        self._current_persona_key = self._persona_manager.list_personas()[0]  # find actual key
        for key in self._persona_manager.list_personas():
            if self._persona_manager.get_persona(key).name == persona.name:
                self._current_persona_key = key
                break
        self._started_at = datetime.now(tz=timezone.utc).isoformat()
        self._transcript = []
        self._current_mood = UserMood.NEUTRAL
        self._current_tone = RequiredTone.PROFESSIONAL

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
        self._session = session
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
                # Detect mood from user speech
                detected_mood = self._detect_mood(event.transcript)
                self._current_mood = detected_mood
                response_tone = _MOOD_TO_TONE.get(detected_mood, RequiredTone.PROFESSIONAL)

                loop.create_task(self._publish_event("transcript", {
                    "speaker": "user",
                    "text": event.transcript,
                    "is_final": True,
                    "mood": detected_mood.value,
                }))

                # Publish mood update for sentiment graph
                loop.create_task(self._publish_event("mood_update", {
                    "mood": detected_mood.value,
                    "tone": response_tone.value,
                }))

                # Dynamically update TTS emotions
                loop.create_task(self._update_emotion(detected_mood))

                self._record_transcript("user", event.transcript, mood=detected_mood.value)
                logger.info("user_speech", text=event.transcript, mood=detected_mood.value)

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
                    self._record_transcript("agent", text_content)

        # Listen for persona switch commands from the frontend
        @ctx.room.on("data_received")
        def on_data_received(data: rtc.DataPacket) -> None:
            try:
                msg = json.loads(data.data.decode())
                if msg.get("type") == "persona_switch":
                    new_persona_key = msg.get("persona")
                    if new_persona_key and self._tonality_mapper and self._session:
                        loop.create_task(
                            self._handle_persona_switch(new_persona_key)
                        )
            except (json.JSONDecodeError, KeyError):
                pass

        # Save conversation when the session closes
        @session.on("close")
        def on_session_close(event) -> None:
            loop.create_task(self._save_conversation())
            logger.info("session_closed", turns=len(self._transcript))

        # Publish initial state
        await self._publish_event("agent_state", {"state": "idle"})
        await self._publish_event("persona_change", {"persona": self._current_persona_key})
        await self._publish_event("mood_update", {"mood": "neutral", "tone": "professional"})

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
