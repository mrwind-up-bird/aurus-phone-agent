"""Main voice agent — orchestrates STT, LLM, TTS with persona routing and emotion engine.

v2: Voice-based sentiment detection via prosodic analysis + keyword fusion.
    Disabled pre-recorded fillers in favor of natural conversational flow.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
import numpy as np
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

from .call_metrics import CallMetrics
from .conversation_store import ConversationRecord, ConversationStore, TranscriptItem
from .models import LeadMetadata, RequiredTone, UserMood
from .persona_manager import PersonaManager
from .prosody_analyzer import ProsodyAnalyzer, ProsodyFeatures
from .tonality_mapper import TonalityMapper
from .voice_sentiment import VoiceSentimentDetector

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

# Audio processing constants
_PROSODY_SAMPLE_RATE = 16000  # Match Deepgram's expected rate
_PROSODY_BUFFER_MAX = 200  # Max frames to buffer between utterances (~4s)

# System prompt — persona addon gets injected at runtime
SYSTEM_PROMPT = """Du bist ein KI-Telefonassistent der Firma Aurus. Du führst professionelle
Verkaufsgespräche auf Deutsch. Aurus bietet KI-gestützte Vertriebsautomatisierung — intelligente
Erstansprache, Lead-Qualifizierung in Echtzeit und nahtlose CRM-Integration.

{persona_addon}

Gesprächsphasen (folge diesem natürlichen Ablauf):
1. BEGRÜSSUNG — Stelle dich vor, nenne den Grund deines Anrufs, frage ob es passt
2. QUALIFIZIERUNG — Finde heraus welche Rolle/Verantwortung, aktuelle Herausforderungen, bestehende Tools
3. PITCH — Verbinde Aurus-Vorteile mit den genannten Herausforderungen. Nenne konkrete Zahlen:
   - 3x mehr qualifizierte Leads pro Tag
   - 40% weniger manuelle Arbeit im Vertrieb
   - Integration in unter 48 Stunden
4. EINWANDBEHANDLUNG — Häufige Einwände und Antworten:
   - "Zu teuer" → "Unsere Kunden sehen ROI in den ersten 30 Tagen. Wir bieten eine kostenlose Testphase."
   - "Keine Zeit" → "Gerade deshalb — Aurus spart Ihrem Team 15+ Stunden pro Woche."
   - "Haben wir schon" → "Welches Tool nutzen Sie? Unsere Kunden wechseln oft wegen der deutschen Sprachqualität."
   - "Muss ich intern besprechen" → "Absolut verständlich. Soll ich Ihnen eine kurze Zusammenfassung per Email schicken?"
5. ABSCHLUSS — Biete einen konkreten nächsten Schritt an: Demo-Termin, Testaccount, Unterlagen
6. FOLLOW-UP — Bestätige Vereinbartes, bedanke dich professionell

Regeln:
- Antworte IMMER auf Deutsch
- Halte Antworten kurz und natürlich (1-3 Sätze)
- Sei höflich aber direkt
- Stelle offene Fragen um das Gespräch voranzutreiben
- Höre aktiv zu und greife die Worte des Gesprächspartners auf
- Wenn kein Interesse: bedanke dich höflich, biete Unterlagen an, beende professionell
- Verwende KEINE englischen Begriffe — alles auf Deutsch
- Sprich den Gesprächspartner mit Namen an wenn bekannt"""


class AurusVoiceAgent:
    """The main Aurus voice agent with persona routing and voice-based emotion engine."""

    def __init__(self) -> None:
        self._persona_manager = PersonaManager()
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
        self._manual_tone_override: bool = False
        self._tone_override_turns_remaining: int = 0
        self._metrics: CallMetrics | None = None

        # Voice sentiment engine
        self._prosody_analyzer = ProsodyAnalyzer(sample_rate=_PROSODY_SAMPLE_RATE)
        self._sentiment_detector = VoiceSentimentDetector(window_size=5)
        self._prosody_buffer: deque[ProsodyFeatures] = deque(maxlen=_PROSODY_BUFFER_MAX)
        self._prosody_lock = asyncio.Lock()
        self._audio_task: asyncio.Task | None = None
        self._audio_stream_active: bool = False

    def _aggregate_prosody(self) -> ProsodyFeatures:
        """Aggregate buffered prosody features into a single per-utterance summary."""
        if not self._prosody_buffer:
            return ProsodyFeatures()

        voiced_frames = [f for f in self._prosody_buffer if f.is_voiced]
        if not voiced_frames:
            return ProsodyFeatures()

        pitch_values = [f.pitch_hz for f in voiced_frames]
        return ProsodyFeatures(
            rms_energy=float(np.mean([f.rms_energy for f in voiced_frames])),
            pitch_hz=float(np.mean(pitch_values)),
            pitch_variance=float(np.std(pitch_values)),  # True std dev across utterance
            energy_ratio=float(np.mean([f.energy_ratio for f in voiced_frames])),
            speaking_rate=float(np.mean([f.speaking_rate for f in voiced_frames])),
            is_voiced=True,
        )

    async def _consume_prosody(self) -> ProsodyFeatures:
        """Thread-safe consume: aggregate and clear prosody buffer under lock."""
        async with self._prosody_lock:
            result = self._aggregate_prosody()
            self._prosody_buffer.clear()
            return result

    async def _process_audio_stream(self, participant: rtc.RemoteParticipant) -> None:
        """Background task: stream user audio and extract prosodic features.

        Runs continuously while the call is active. Feeds ProsodyAnalyzer
        with 20ms audio frames and buffers the results for per-utterance
        aggregation when transcription events fire.
        """
        logger.info("prosody_stream_started", participant=participant.identity)
        audio_stream: rtc.AudioStream | None = None

        try:
            audio_stream = rtc.AudioStream.from_participant(
                participant=participant,
                track_source=rtc.TrackSource.SOURCE_MICROPHONE,
                sample_rate=_PROSODY_SAMPLE_RATE,
                num_channels=1,
            )
            self._audio_stream_active = True

            async for event in audio_stream:
                frame = event.frame
                if frame.samples_per_channel < 16:
                    continue

                # Convert audio frame to numpy array for analysis
                audio_data = np.frombuffer(frame.data, dtype=np.int16)

                features = self._prosody_analyzer.analyze_frame(
                    audio_data, sample_rate=frame.sample_rate
                )
                async with self._prosody_lock:
                    self._prosody_buffer.append(features)

        except asyncio.CancelledError:
            logger.info("prosody_stream_cancelled")
        except Exception as exc:
            logger.warning("prosody_stream_error", error=str(exc))
        finally:
            if audio_stream is not None:
                await audio_stream.aclose()
            self._audio_stream_active = False

    async def _update_emotion(self, mood: UserMood) -> None:
        """Update TTS emotions based on detected user mood."""
        if not self._tonality_mapper or not self._session:
            return

        # If manual tone override is active, decrement and skip
        if self._manual_tone_override:
            self._tone_override_turns_remaining -= 1
            if self._tone_override_turns_remaining <= 0:
                self._manual_tone_override = False
                logger.info("tone_override_expired")
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
        logger.info(
            "emotion_updated",
            mood=mood.value,
            tone=tone.value,
            emotions=mapped["emotions"],
        )

    async def _apply_tone_shift(self, tone: RequiredTone) -> None:
        """Apply a manual tone shift from the operator dashboard."""
        if not self._tonality_mapper or not self._session:
            return

        self._current_tone = tone
        self._manual_tone_override = True
        self._tone_override_turns_remaining = 3

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

        # Notify frontend of the tone change
        await self._publish_event("mood_update", {
            "mood": self._current_mood.value,
            "tone": tone.value,
        })

        logger.info("tone_shift_applied", tone=tone.value, emotions=mapped["emotions"])

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
        """Hot-swap the agent persona during a live call."""
        if not self._tonality_mapper or not self._session:
            return

        try:
            new_persona = self._persona_manager.get_persona(new_persona_key)
        except KeyError:
            logger.warning("persona_switch_failed_unknown_key", key=new_persona_key)
            return

        self._tonality_mapper.update_persona(new_persona)
        default_tone = self._tonality_mapper.map_tone(RequiredTone.NEUTRAL)
        system_prompt = SYSTEM_PROMPT.format(persona_addon=new_persona.system_prompt_addon)

        new_agent = Agent(
            instructions=system_prompt,
            stt=deepgram.STT(language="de", model="nova-3"),
            llm=openai.LLM(model="gpt-4o", temperature=0.7),
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

        self._session.update_agent(new_agent)

        self._persona_name = new_persona.name
        self._current_persona_key = new_persona_key
        self._current_tone = RequiredTone.NEUTRAL

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

    @staticmethod
    def _build_greeting(lead: LeadMetadata, persona_name: str) -> str:
        """Build a time-aware, personalized German greeting."""
        hour = datetime.now().hour
        if hour < 12:
            time_greeting = "Guten Morgen"
        elif hour < 18:
            time_greeting = "Guten Tag"
        else:
            time_greeting = "Guten Abend"

        name_part = ""
        if lead.name and lead.name != "Unknown Lead":
            if lead.gender.lower() in ("male", "m", "männlich", "herr"):
                name_part = f", Herr {lead.name.split()[-1]}"
            elif lead.gender.lower() in ("female", "f", "weiblich", "frau"):
                name_part = f", Frau {lead.name.split()[-1]}"
            else:
                name_part = f", {lead.name.split()[0]}"

        company_part = ""
        if lead.company:
            company_part = f" Ich rufe an bezüglich {lead.company}."

        return (
            f"{time_greeting}{name_part}. Hier ist {persona_name} von Aurus."
            f"{company_part} Haben Sie einen kurzen Moment Zeit?"
        )

    async def _generate_ai_summary(self, transcript: list[TranscriptItem]) -> str:
        """Generate an intelligent call summary using GPT-4o."""
        if not transcript:
            return "Kein Gespräch aufgezeichnet."

        lines = []
        for item in transcript:
            speaker = "Agent" if item.speaker == "agent" else "Anrufer"
            lines.append(f"{speaker}: {item.text}")
        conversation_text = "\n".join(lines)

        metrics_text = ""
        if self._metrics:
            snap = self._metrics.snapshot()
            metrics_text = (
                f"\nKennzahlen: {snap['turn_count']} Gesprächsrunden, "
                f"Lead-Score: {snap['lead_score']}/100, "
                f"Stimmungsverlauf: {snap['mood_trajectory']}, "
                f"Einwände: {snap['objection_count']}"
            )

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=200,
                messages=[{
                    "role": "system",
                    "content": "Du bist ein Vertriebsanalyst. Erstelle eine knappe deutsche Zusammenfassung des Telefongesprächs (2-3 Sätze). Nenne: Gesprächsergebnis, Stimmung des Leads, und nächste Schritte falls vereinbart."
                }, {
                    "role": "user",
                    "content": f"Gespräch:\n{conversation_text}{metrics_text}"
                }],
            )
            return response.choices[0].message.content or "Zusammenfassung nicht verfügbar."
        except Exception as exc:
            logger.warning("ai_summary_failed", error=str(exc))
            return f"Gespräch mit {len(transcript)} Austauschen. Automatische Zusammenfassung fehlgeschlagen."

    async def _save_conversation(self) -> None:
        """Persist the current conversation to disk with AI-generated summary."""
        lead_meta = (
            self._lead.model_dump() if self._lead else {"name": "Unknown Lead"}
        )
        lead_meta_str = {k: str(v) for k, v in lead_meta.items()}

        outcome = self._outcome
        if self._metrics:
            score = self._metrics.lead_score
            stage = self._metrics.stage
            if stage in ("closing", "follow_up") and score >= 60:
                outcome = "interested"
            elif score >= 80:
                outcome = "booked"
            elif score <= 20:
                outcome = "declined"

        summary = await self._generate_ai_summary(self._transcript)

        record = ConversationRecord(
            lead_metadata=lead_meta_str,
            persona_used=self._persona_name,
            transcript=list(self._transcript),
            started_at=self._started_at,
            ended_at=datetime.now(tz=timezone.utc).isoformat(),
            outcome=outcome,
            summary=summary,
        )
        try:
            filepath = await self._conversation_store.save(record)
            logger.info("conversation_persisted", path=str(filepath), turns=len(self._transcript))
        except Exception as exc:
            logger.error("conversation_save_failed", error=str(exc))

        metrics_snap = self._metrics.snapshot() if self._metrics else {}
        await self._publish_event("call_summary", {
            "outcome": outcome,
            "summary": summary,
            "lead_score": metrics_snap.get("lead_score", 0),
            "turn_count": metrics_snap.get("turn_count", 0),
            "duration_seconds": metrics_snap.get("duration_seconds", 0),
            "mood_trajectory": metrics_snap.get("mood_trajectory", "stable"),
        })

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
        self._current_persona_key = self._persona_manager.list_personas()[0]
        for key in self._persona_manager.list_personas():
            if self._persona_manager.get_persona(key).name == persona.name:
                self._current_persona_key = key
                break
        self._started_at = datetime.now(tz=timezone.utc).isoformat()
        self._transcript = []
        self._current_mood = UserMood.NEUTRAL
        self._current_tone = RequiredTone.PROFESSIONAL
        self._metrics = CallMetrics()

        # Reset voice sentiment engine for fresh call
        self._prosody_analyzer.reset()
        self._sentiment_detector.reset()
        self._prosody_buffer.clear()

        # Get default emotion settings for this persona
        default_tone = self._tonality_mapper.map_tone(RequiredTone.NEUTRAL)

        logger.info(
            "agent_starting",
            lead=lead.name,
            persona=persona.name,
            room=ctx.room.name,
            emotions=default_tone["emotions"],
        )

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
        loop = asyncio.get_running_loop()

        # --- Start prosody analysis when remote participant's audio is subscribed ---
        @ctx.room.on("track_subscribed")
        def on_track_subscribed(
            track: rtc.RemoteTrack,
            publication: rtc.RemoteTrackPublication,
            participant: rtc.RemoteParticipant,
        ) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                # Cancel previous audio task if any
                if self._audio_task and not self._audio_task.done():
                    self._audio_task.cancel()
                self._audio_task = loop.create_task(
                    self._process_audio_stream(participant)
                )
                logger.info("prosody_analysis_attached", participant=participant.identity)

        # --- Event handlers for frontend broadcasting (must be sync — use create_task) ---
        @session.on("agent_state_changed")
        def on_agent_state_changed(event) -> None:
            new_state = event.new_state
            loop.create_task(self._publish_event("agent_state", {"state": new_state}))
            logger.debug("agent_state_changed", state=new_state)

        async def _handle_final_transcription(transcript: str) -> None:
            """Process a final user transcription with prosody-based sentiment."""
            # Thread-safe consume of prosody buffer
            prosody = await self._consume_prosody()

            # Hybrid mood detection: voice prosody + text keywords
            sentiment = self._sentiment_detector.detect(
                text=transcript,
                prosody=prosody if prosody.is_voiced else None,
            )
            detected_mood = sentiment.mood
            self._current_mood = detected_mood
            response_tone = _MOOD_TO_TONE.get(detected_mood, RequiredTone.PROFESSIONAL)

            await self._publish_event("transcript", {
                "speaker": "user",
                "text": transcript,
                "is_final": True,
                "mood": detected_mood.value,
            })

            await self._publish_event("mood_update", {
                "mood": detected_mood.value,
                "tone": response_tone.value,
            })

            await self._update_emotion(detected_mood)

            if self._metrics:
                self._metrics.record_user_turn(transcript, detected_mood.value)
                await self._publish_event("call_metrics", self._metrics.snapshot())

            self._record_transcript("user", transcript, mood=detected_mood.value)
            logger.info(
                "user_speech",
                text=transcript,
                mood=detected_mood.value,
                sentiment_source=sentiment.source,
                confidence=round(sentiment.confidence, 2),
                prosody_mood=sentiment.prosody_mood.value if sentiment.prosody_mood else None,
                keyword_mood=sentiment.keyword_mood.value if sentiment.keyword_mood else None,
                energy_ratio=round(prosody.energy_ratio, 2) if prosody.is_voiced else None,
                pitch_variance=round(prosody.pitch_variance, 1) if prosody.is_voiced else None,
            )

        @session.on("user_input_transcribed")
        def on_user_input(event) -> None:
            if event.is_final:
                loop.create_task(_handle_final_transcription(event.transcript))

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

                    if self._metrics:
                        self._metrics.record_agent_turn()
                        loop.create_task(self._publish_event("call_metrics", self._metrics.snapshot()))

        # Listen for persona switch / tone shift commands from the frontend
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
                elif msg.get("type") == "tone_shift":
                    tone_str = msg.get("tone")
                    if tone_str and self._tonality_mapper and self._session:
                        try:
                            tone = RequiredTone(tone_str)
                            loop.create_task(self._apply_tone_shift(tone))
                        except ValueError:
                            pass
            except (json.JSONDecodeError, KeyError):
                pass

        # Save conversation when the session closes
        @session.on("close")
        def on_session_close(event) -> None:
            # Cancel audio processing
            if self._audio_task and not self._audio_task.done():
                self._audio_task.cancel()
            if loop.is_running():
                loop.create_task(self._save_conversation())
            else:
                logger.warning("session_close_loop_not_running", turns=len(self._transcript))
            logger.info("session_closed", turns=len(self._transcript))

        # Publish initial state
        await self._publish_event("agent_state", {"state": "idle"})
        await self._publish_event("persona_change", {"persona": self._current_persona_key})
        await self._publish_event("mood_update", {"mood": "neutral", "tone": "professional"})
        await self._publish_event("call_metrics", self._metrics.snapshot())

        await session.start(agent=agent, room=ctx.room)

        # NOTE: BackgroundAudioPlayer with pre-recorded fillers has been disabled.
        # The natural conversational flow with fast STT→LLM→TTS pipeline provides
        # better UX than artificial filler sounds that don't match the persona voice.

        # Agent speaks first — proactive greeting (critical for cold calling)
        greeting = self._build_greeting(lead, persona.name)
        await session.say(greeting, allow_interruptions=True)
        self._record_transcript("agent", greeting)

        logger.info("agent_session_started", persona=persona.name, greeting=greeting)

    def _extract_lead_metadata(self, ctx: JobContext) -> LeadMetadata:
        """Extract lead metadata from LiveKit room metadata."""
        try:
            if ctx.room.metadata:
                data = json.loads(ctx.room.metadata)
                return LeadMetadata(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("lead_metadata_parse_failed", error=str(e))

        return LeadMetadata(name="Unknown Lead")


async def _entrypoint(ctx: JobContext) -> None:
    """Per-job entrypoint — creates a fresh agent instance for each call."""
    agent = AurusVoiceAgent()
    await agent.entrypoint(ctx)


def create_app() -> None:
    """Create and run the LiveKit agents application."""
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=_entrypoint,
            agent_name="aurus-voice-agent",
        )
    )


if __name__ == "__main__":
    create_app()
