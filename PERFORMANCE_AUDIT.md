# Performance & Latency Audit — Aurus Voice Agent

**Date:** 2026-02-19
**Auditor:** Performance Architect (automated)
**Target:** Sub-500ms time-to-first-byte (TTFB) for agent responses
**Scope:** Agent backend (`/agent`), frontend dashboard (`/frontend`), Docker build

---

## Executive Summary

The Aurus Voice Agent has a **theoretical minimum latency of ~1,800ms** from end-of-user-speech to first agent audio byte, with the primary bottleneck being GPT-4o inference (~1,000-3,000ms). The filler injection system via `BackgroundAudioPlayer` effectively masks this for perceived latency, but several architectural issues add unnecessary overhead:

1. **Agent reconstruction on every emotion change** loads the Silero VAD ML model from disk (~200ms) and creates new STT/LLM/TTS clients — this happens on every user turn where mood changes.
2. **Unbounded list growth** in `CallMetrics` and frontend state arrays creates increasing GC pressure during long calls.
3. **`min_endpointing_delay=0.5`** adds a fixed 500ms to every response, which is the single largest controllable latency contributor.
4. **Synchronous file I/O** in `ConversationStore.save()` blocks the event loop.
5. **Docker image carries full `node_modules`** in the runtime stage (~300-500MB).

**Estimated latency budget (current):**

```
User stops speaking ─────────────── 0ms
  + VAD endpointing delay            500ms
  + Deepgram STT finalization         50-150ms
  + GPT-4o inference                  1,000-3,000ms
  + Cartesia TTS first chunk          100-200ms
  + WebRTC transport                  20-80ms
                                     ─────────────
  Total: ~1,670-3,930ms             (masked by fillers at ~500ms)
```

---

## Latency Path Diagram

```
                     LATENCY PATH (end-to-end)
  ┌──────────────────────────────────────────────────────────────┐
  │                                                              │
  │  User speaks   VAD EOD    STT Final   LLM Response   TTS    │
  │  ─────────── ──────────── ────────── ──────────────  ─────  │
  │       │            │           │            │           │    │
  │       │   500ms    │  50-150ms │  1-3s      │  100-200ms│   │
  │       ├───────────►├──────────►├───────────►├──────────►│   │
  │       │            │           │            │           │    │
  │       │            │ ┌─────────────────┐    │           │    │
  │       │            │ │ BackgroundAudio  │    │           │    │
  │       │            │ │ plays filler     │    │           │    │
  │       │            │ │ (~50ms latency)  │    │           │    │
  │       │            │ └─────────────────┘    │           │    │
  │       │            │                        │           │    │
  │       │            ├── PERCEIVED LATENCY ──►│           │    │
  │       │            │       ~500ms           │           │    │
  └──────────────────────────────────────────────────────────────┘
```

---

## Findings

### PERF-01: Agent Reconstruction on Emotion Change (CRITICAL)

| Field | Value |
|-------|-------|
| **Category** | LATENCY / CPU |
| **Impact** | HIGH |
| **Location** | `agent/src/agent.py:174-187`, `agent/src/agent.py:204-217`, `agent/src/agent.py:266-285` |
| **Frequency** | Every user turn where mood changes + operator tone shifts + persona switches |

**Description:**
Three methods — `_update_emotion()`, `_apply_tone_shift()`, and `_handle_persona_switch()` — each construct a completely new `Agent()` object. Each construction calls `silero.VAD.load()`, which loads a ~2MB ONNX model from disk into memory. Additionally, new `deepgram.STT()`, `openai.LLM()`, and `cartesia.TTS()` client instances are created, each requiring TCP connection setup, TLS handshake, and potential HTTP/2 negotiation.

**Estimated overhead per reconstruction:**
- `silero.VAD.load()`: ~100-200ms (disk I/O + ONNX model parse)
- `deepgram.STT()`: ~10-30ms (object creation, may open connection lazily)
- `openai.LLM()`: ~5-10ms (object creation)
- `cartesia.TTS()`: ~5-10ms (object creation)
- **Total: ~120-250ms per emotion change, blocking the event loop during VAD load**

**Current code (`agent.py:174-187`):**
```python
async def _update_emotion(self, mood: UserMood) -> None:
    # ...
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
        vad=silero.VAD.load(),  # <-- LOADS ML MODEL FROM DISK EVERY TIME
        allow_interruptions=True,
        min_endpointing_delay=0.5,
    )
    self._session.update_agent(new_agent)
```

**Optimization — Cache shared components and use a `_build_agent()` factory:**
```python
class AurusVoiceAgent:
    def __init__(self) -> None:
        # ...
        self._cached_vad: silero.VAD | None = None
        self._cached_stt: deepgram.STT | None = None
        self._cached_llm: openai.LLM | None = None

    def _get_vad(self) -> silero.VAD:
        """Load VAD once and reuse across agent reconstructions."""
        if self._cached_vad is None:
            self._cached_vad = silero.VAD.load()
        return self._cached_vad

    def _get_stt(self) -> deepgram.STT:
        """Reuse STT client — language/model don't change."""
        if self._cached_stt is None:
            self._cached_stt = deepgram.STT(language="de", model="nova-3")
        return self._cached_stt

    def _get_llm(self) -> openai.LLM:
        """Reuse LLM client — model/temperature don't change."""
        if self._cached_llm is None:
            self._cached_llm = openai.LLM(model="gpt-4o", temperature=0.7)
        return self._cached_llm

    def _build_agent(
        self,
        persona: PersonaConfig,
        tone_mapping: dict,
    ) -> Agent:
        """Build an Agent, reusing cached VAD/STT/LLM instances.
        Only TTS is recreated since voice/emotion/speed change per persona/tone.
        """
        return Agent(
            instructions=SYSTEM_PROMPT.format(
                persona_addon=persona.system_prompt_addon
            ),
            stt=self._get_stt(),
            llm=self._get_llm(),
            tts=cartesia.TTS(
                voice=tone_mapping["voice_id"],
                language="de",
                speed=tone_mapping["speed"],
                emotion=tone_mapping["emotions"],
            ),
            vad=self._get_vad(),
            allow_interruptions=True,
            min_endpointing_delay=0.5,
        )
```

Then `_update_emotion()`, `_apply_tone_shift()`, and `_handle_persona_switch()` all call `self._build_agent(persona, mapped)` instead of constructing inline.

**Estimated improvement:** ~120-250ms saved per emotion update. Over a 10-turn call with 5 mood changes, this saves ~600-1,250ms of cumulative blocking time and eliminates ~10MB of transient memory allocations (5 x 2MB VAD model copies).

**NOTE:** Verify that the LiveKit agents SDK `session.update_agent()` does not close/invalidate the previous STT/LLM instances. If it does, only VAD caching is safe. Test with a single `_cached_vad` first.

---

### PERF-02: Unbounded `mood_history` and `response_times` Lists (MEDIUM)

| Field | Value |
|-------|-------|
| **Category** | MEMORY |
| **Impact** | MEDIUM (grows linearly with call duration) |
| **Location** | `agent/src/call_metrics.py:32-34` |

**Description:**
`CallMetrics.mood_history` and `CallMetrics.response_times` are plain lists that grow without bound. For a typical 10-minute call with ~20 turns, this is negligible. But the `lead_score` property iterates the entire `mood_history` on every call (line 72), and `avg_response_time_ms` sums the entire `response_times` list (line 50). For abnormally long calls (>100 turns), this creates O(n) computation on every metrics snapshot.

**Current code (`call_metrics.py:32-34`):**
```python
mood_history: list[str] = field(default_factory=list)
response_times: list[float] = field(default_factory=list)
```

**Optimization — Use `collections.deque` with maxlen:**
```python
from collections import deque

mood_history: deque[str] = field(default_factory=lambda: deque(maxlen=100))
response_times: deque[float] = field(default_factory=lambda: deque(maxlen=50))
```

Also update `lead_score` to only weight the last N moods (it already conceptually weights recent moods more, so capping at 100 loses nothing).

**Estimated improvement:** Caps memory at ~5KB regardless of call length. Prevents pathological O(n) growth in `snapshot()` calls.

---

### PERF-03: `min_endpointing_delay=0.5` Adds 500ms Fixed Latency (HIGH)

| Field | Value |
|-------|-------|
| **Category** | LATENCY |
| **Impact** | HIGH — single largest controllable latency contributor |
| **Location** | `agent/src/agent.py:186`, `agent/src/agent.py:216`, `agent/src/agent.py:284`, `agent/src/agent.py:504` |

**Description:**
`min_endpointing_delay=0.5` tells the VAD to wait 500ms after detecting end-of-speech before confirming it. This prevents false positives (cutting off mid-sentence) but adds a flat 500ms to every response. For a competition targeting sub-500ms TTFB, this single setting consumes the entire budget.

**Trade-off analysis:**
- `0.5s` — Safe but slow. Good for production telephony.
- `0.3s` — Aggressive. May occasionally cut off trailing words ("...ja, also, ähm").
- `0.2s` — Very aggressive. Will cause interruptions on hesitant speakers.

**Optimization:**
```python
min_endpointing_delay=0.3,  # Save 200ms, acceptable for demo/competition
```

For the competition, consider `0.25` with the understanding that fillers mask any awkwardness. In production, keep `0.5`.

**Estimated improvement:** 200ms saved per turn (with 0.3), or 300ms (with 0.2).

---

### PERF-04: Synchronous File I/O in Async Context (MEDIUM)

| Field | Value |
|-------|-------|
| **Category** | LATENCY / CPU |
| **Impact** | MEDIUM (blocks event loop on call end) |
| **Location** | `agent/src/conversation_store.py:104` |

**Description:**
`ConversationStore.save()` is declared `async` but calls `filepath.write_text()` which is synchronous file I/O. This blocks the event loop for the duration of the write (~1-5ms for small JSON, but potentially longer on networked/Docker volumes).

Similarly, `ConversationStore.load()` (line 116) and `list_all()` (line 133-134) perform synchronous file reads in a loop.

**Current code (`conversation_store.py:104`):**
```python
async def save(self, record: ConversationRecord) -> Path:
    # ...
    filepath.write_text(record.model_dump_json(indent=2), encoding="utf-8")
```

**Optimization:**
```python
import asyncio

async def save(self, record: ConversationRecord) -> Path:
    # ...
    content = record.model_dump_json(indent=2)
    await asyncio.to_thread(filepath.write_text, content, encoding="utf-8")
    return filepath
```

Similarly for `load()` and `list_all()`:
```python
async def load(self, conversation_id: str) -> ConversationRecord | None:
    for filepath in self._base_dir.glob("*.json"):
        try:
            text = await asyncio.to_thread(filepath.read_text, encoding="utf-8")
            record = ConversationRecord.model_validate_json(text)
            if record.id == conversation_id:
                return record
        except Exception as exc:
            logger.warning("conversation_load_error", file=filepath.name, error=str(exc))
    return None
```

**Estimated improvement:** Prevents event loop blocking during save/load. Critical for Docker volumes where I/O latency can spike to 50-200ms.

---

### PERF-05: `list_all()` Loads Every JSON File into Memory (MEDIUM)

| Field | Value |
|-------|-------|
| **Category** | MEMORY / LATENCY |
| **Impact** | MEDIUM (scales with conversation history size) |
| **Location** | `agent/src/conversation_store.py:130-145` |

**Description:**
`list_all()` deserializes every JSON file in the conversations directory into full `ConversationRecord` objects, including their complete transcripts. After 100 calls with ~20 turns each, this loads ~200KB+ of transcript data just to list summaries. `list_by_lead()` (line 147-155) calls `list_all()` to filter, making it even worse.

**Optimization — Lazy loading with summary index:**
```python
async def list_summaries(self) -> list[dict]:
    """Return lightweight summaries without full transcript data."""
    summaries = []
    for filepath in sorted(self._base_dir.glob("*.json"), reverse=True):
        try:
            text = await asyncio.to_thread(filepath.read_text, encoding="utf-8")
            data = json.loads(text)
            summaries.append({
                "id": data.get("id"),
                "lead_name": data.get("lead_metadata", {}).get("name", "Unknown"),
                "persona": data.get("persona_used", ""),
                "started_at": data.get("started_at", ""),
                "outcome": data.get("outcome", ""),
                "message_count": len(data.get("transcript", [])),
                "summary": data.get("summary", ""),
            })
        except Exception:
            continue
    return summaries
```

Alternatively, maintain a lightweight `_index.json` file updated on each save.

**Estimated improvement:** Reduces memory usage from O(n * transcript_size) to O(n * summary_size) for listing. For 100 conversations, ~10x memory reduction.

---

### PERF-06: Frontend Audio Element Leak (LOW-MEDIUM)

| Field | Value |
|-------|-------|
| **Category** | MEMORY |
| **Impact** | LOW-MEDIUM (cumulative over reconnections) |
| **Location** | `frontend/src/hooks/use-agent-connection.ts:119-123` |

**Description:**
`handleTrackSubscribed` creates a new `<audio>` element via `document.createElement("audio")` and appends it to `document.body`. The cleanup in `handleTrackUnsubscribed` (line 135) removes it by ID. However, if the track is subscribed/unsubscribed rapidly (e.g., network flap) or if the component unmounts before unsubscribe fires, orphaned audio elements accumulate.

**Current code (`use-agent-connection.ts:119-123`):**
```typescript
const audioEl = document.createElement("audio");
audioEl.srcObject = stream;
audioEl.autoplay = true;
audioEl.id = `agent-audio-${participant.identity}`;
document.body.appendChild(audioEl);
```

**Optimization — Clean up existing element before creating new one:**
```typescript
const handleTrackSubscribed = useCallback(
  (track: RemoteTrack, publication: RemoteTrackPublication, participant: RemoteParticipant) => {
    if (track.kind === Track.Kind.Audio) {
      // Clean up any existing audio element for this participant
      const existingEl = document.getElementById(`agent-audio-${participant.identity}`);
      if (existingEl) {
        (existingEl as HTMLAudioElement).srcObject = null;
        existingEl.remove();
      }

      const stream = new MediaStream([track.mediaStreamTrack]);
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
```

Also add cleanup to the `disconnect()` callback:
```typescript
const disconnect = useCallback(() => {
  // Clean up all agent audio elements
  document.querySelectorAll('[id^="agent-audio-"]').forEach((el) => {
    (el as HTMLAudioElement).srcObject = null;
    el.remove();
  });
  roomRef.current?.disconnect();
  // ... rest of cleanup
}, []);
```

**Estimated improvement:** Prevents orphaned audio elements and associated MediaStream objects from accumulating.

---

### PERF-07: Frontend Unbounded State Array Growth (MEDIUM)

| Field | Value |
|-------|-------|
| **Category** | MEMORY |
| **Impact** | MEDIUM (GC pressure increases over long calls) |
| **Location** | `frontend/src/hooks/use-agent-connection.ts:68-75` (moodHistory), `frontend/src/hooks/use-agent-connection.ts:84-92` (transcript) |

**Description:**
`moodHistory` and `transcript` state arrays grow without bound via spread operator `[...prev, newItem]`. Each state update creates a new array, copying all previous entries. For a 30-minute call with 60 transcript entries and 30 mood updates:
- Each transcript update copies the entire array: O(n) copies
- Total allocations: 1+2+3+...+60 = 1,830 string copies
- React re-renders the entire component tree on each update

**Current code (`use-agent-connection.ts:84-92`):**
```typescript
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
```

**Optimization — Cap array length with sliding window:**
```typescript
const MAX_TRANSCRIPT_ENTRIES = 200;
const MAX_MOOD_ENTRIES = 100;

case "transcript":
  setTranscript((prev) => {
    const next = [
      ...prev,
      {
        speaker: event.data.speaker,
        text: event.data.text,
        timestamp: Date.now() / 1000,
        mood: event.data.mood,
      },
    ];
    return next.length > MAX_TRANSCRIPT_ENTRIES
      ? next.slice(-MAX_TRANSCRIPT_ENTRIES)
      : next;
  });
  break;

case "mood_update":
  setMoodHistory((prev) => {
    const next = [
      ...prev,
      {
        timestamp: Date.now() / 1000,
        mood: event.data.mood as UserMood,
        tone: event.data.tone as RequiredTone,
      },
    ];
    return next.length > MAX_MOOD_ENTRIES
      ? next.slice(-MAX_MOOD_ENTRIES)
      : next;
  });
  break;
```

**Estimated improvement:** Caps memory at ~50KB for transcript, ~10KB for mood. Prevents O(n^2) cumulative copy overhead.

---

### PERF-08: `handlePersonaSwitch` / `handleToneShift` Recreated on Every Render (LOW)

| Field | Value |
|-------|-------|
| **Category** | CPU |
| **Impact** | LOW (causes unnecessary child re-renders) |
| **Location** | `frontend/src/app/page.tsx:87-99` |

**Description:**
`handlePersonaSwitch` and `handleToneShift` have `[connection]` in their dependency arrays. Since `connection` is the return value of `useAgentConnection()` and is a new object on every render (hooks return new objects), these callbacks are recreated on every render, causing `PersonaSwitcher` and `SentimentCoaching` to re-render unnecessarily.

**Current code (`page.tsx:87-99`):**
```typescript
const handlePersonaSwitch = useCallback(
  (key: string) => {
    connection.sendPersonaSwitch(key);
  },
  [connection]  // <-- recreated every render
);
```

**Optimization — Use stable refs:**
```typescript
const handlePersonaSwitch = useCallback(
  (key: string) => {
    connection.sendPersonaSwitch(key);
  },
  [connection.sendPersonaSwitch]  // <-- stable (useCallback with [] deps)
);

const handleToneShift = useCallback(
  (tone: RequiredTone) => {
    connection.sendToneShift(tone);
  },
  [connection.sendToneShift]  // <-- stable
);
```

**Estimated improvement:** Eliminates ~2-4 unnecessary child component re-renders per data channel message. Minimal wall-clock impact but reduces React reconciliation work.

---

### PERF-09: Keyboard Handler Recreated on Every Render (LOW)

| Field | Value |
|-------|-------|
| **Category** | CPU |
| **Impact** | LOW |
| **Location** | `frontend/src/app/page.tsx:102-133` |

**Description:**
The `useEffect` for keyboard shortcuts has `[connection]` as a dependency. Since `connection` is a new object each render, this effect tears down and re-attaches the `keydown` listener on every render cycle. This means `removeEventListener` + `addEventListener` on every state change.

**Optimization — Depend on stable function references:**
```typescript
useEffect(() => {
  const handler = (e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
    switch (e.key) {
      case "1": connection.sendPersonaSwitch("lukas"); break;
      // ...
    }
  };
  window.addEventListener("keydown", handler);
  return () => window.removeEventListener("keydown", handler);
}, [connection.sendPersonaSwitch, connection.dismissSummary]);
```

**Estimated improvement:** Eliminates ~10-20 unnecessary listener re-attachments per second during active calls.

---

### PERF-10: AudioVisualizer Runs `requestAnimationFrame` Continuously (LOW-MEDIUM)

| Field | Value |
|-------|-------|
| **Category** | CPU / BATTERY |
| **Impact** | LOW-MEDIUM (60fps GPU/CPU usage even when idle) |
| **Location** | `frontend/src/components/audio-visualizer.tsx:58-118` |

**Description:**
The `draw()` function runs via `requestAnimationFrame` at 60fps continuously, even in `idle` state. It creates a new `LinearGradient` per bar (40 bars x 60fps = 2,400 gradient objects/second). While modern browsers handle this efficiently, it drains battery on mobile devices and contributes to overall CPU load.

**Optimization — Reduce frame rate when idle and batch gradients:**
```typescript
function draw() {
  // ... existing draw logic ...

  // Throttle to 15fps when idle
  if (state === "idle" || state === "initializing") {
    setTimeout(() => {
      animationRef.current = requestAnimationFrame(draw);
    }, 66); // ~15fps
  } else {
    animationRef.current = requestAnimationFrame(draw);
  }
}
```

Also, pre-compute the gradient pair once per state change instead of per-bar:
```typescript
// Outside the bar loop — one gradient for all bars of the same color
const [color1, color2] = STATE_COLORS[state] || STATE_COLORS.idle;
```
This is already done (line 85), but the gradient is recreated per-bar inside the loop (line 94). Consider using `ctx.fillStyle` with a solid color for idle state.

**Estimated improvement:** ~75% CPU reduction during idle state. Noticeable battery improvement on mobile.

---

### PERF-11: `_generate_ai_summary()` Creates New OpenAI Client on Every Call (LOW)

| Field | Value |
|-------|-------|
| **Category** | LATENCY / MEMORY |
| **Impact** | LOW (only called once at call end) |
| **Location** | `agent/src/agent.py:365-366` |

**Description:**
`_generate_ai_summary()` imports and instantiates `AsyncOpenAI()` inline every call. While this only happens once per call (on close), the import + instantiation adds ~50ms and creates an unnecessary HTTP client with its own connection pool.

**Current code (`agent.py:365-366`):**
```python
from openai import AsyncOpenAI
client = AsyncOpenAI()
```

**Optimization — Move import to module level and reuse client:**
```python
# At module level
from openai import AsyncOpenAI
_openai_client = AsyncOpenAI()

# In _generate_ai_summary:
async def _generate_ai_summary(self, transcript: list[TranscriptItem]) -> str:
    # ...
    response = await _openai_client.chat.completions.create(...)
```

**Estimated improvement:** ~50ms saved at call end. Minor.

---

### PERF-12: Docker Image Size — Full `node_modules` in Runtime (BUILD)

| Field | Value |
|-------|-------|
| **Category** | BUILD / NETWORK |
| **Impact** | MEDIUM (affects deploy speed) |
| **Location** | `Dockerfile:45-46` |

**Description:**
The frontend runtime stage copies the entire `node_modules` directory from the builder:
```dockerfile
COPY --from=frontend-builder /app/frontend/node_modules ./node_modules
```
Next.js 15 with `output: "standalone"` can produce a self-contained build that only includes required modules, reducing the image from ~500MB to ~50-100MB.

**Optimization:**
1. Add to `next.config.js`:
```javascript
module.exports = {
  output: "standalone",
};
```

2. Update Dockerfile:
```dockerfile
# ---- Frontend Runtime ----
FROM node:22-slim AS frontend

WORKDIR /app/frontend

# Copy only the standalone build (no full node_modules)
COPY --from=frontend-builder /app/frontend/.next/standalone ./
COPY --from=frontend-builder /app/frontend/.next/static ./.next/static
COPY --from=frontend-builder /app/frontend/public ./public

ENV NODE_ENV=production
EXPOSE 3000

CMD ["node", "server.js"]
```

**Estimated improvement:** Image size reduction from ~500MB to ~80-100MB. Faster deploys, lower bandwidth.

---

### PERF-13: Agent `create_app()` Creates Single Instance for All Calls (LOW)

| Field | Value |
|-------|-------|
| **Category** | MEMORY |
| **Impact** | LOW (state leak between calls) |
| **Location** | `agent/src/agent.py:638-646` |

**Description:**
`create_app()` creates a single `AurusVoiceAgent()` instance and reuses it for all incoming calls via `entrypoint_fnc=agent.entrypoint`. While `entrypoint()` resets most state, `_persona_manager` and `_conversation_store` persist across calls — which is fine — but `_transcript`, `_lead`, `_metrics` etc. from the previous call remain in memory until the next call starts.

**Optimization:** Consider creating a new `AurusVoiceAgent` per call or explicitly clearing state:
```python
# At the start of entrypoint():
self._transcript = []
self._lead = None
self._metrics = None
self._current_mood = UserMood.NEUTRAL
self._current_tone = RequiredTone.PROFESSIONAL
```

This is already partially done (line 467-470) but could be more thorough.

**Estimated improvement:** Minimal. Prevents stale data from previous calls lingering in memory.

---

### PERF-14: Duplicate Transcript Entries from Data Channel + TranscriptionReceived (LOW)

| Field | Value |
|-------|-------|
| **Category** | NETWORK / MEMORY |
| **Impact** | LOW |
| **Location** | `frontend/src/hooks/use-agent-connection.ts:83-92` and `frontend/src/hooks/use-agent-connection.ts:177-191` |

**Description:**
Transcript entries can be added from two sources:
1. Custom `data_received` events (`type: "transcript"`) sent by the agent (line 83-92)
2. LiveKit's built-in `TranscriptionReceived` events (line 177-191)

If both fire for the same utterance, duplicates appear in the transcript. This doubles memory usage for transcript and causes visual duplication.

**Optimization:** Either:
- Disable `TranscriptionReceived` handling and rely solely on custom data channel events (which include mood data), OR
- Add deduplication by timestamp/text fingerprint, OR
- Use only `TranscriptionReceived` and add mood data separately.

**Estimated improvement:** Eliminates duplicate entries. ~50% transcript memory reduction if both sources fire.

---

### PERF-15: `_detect_mood()` and `_detect_stage()` Linear Keyword Scanning (LOW)

| Field | Value |
|-------|-------|
| **Category** | CPU |
| **Impact** | LOW (fast enough for current keyword counts) |
| **Location** | `agent/src/agent.py:139-149`, `agent/src/call_metrics.py:137-154` |

**Description:**
Both `_detect_mood()` and `_detect_stage()` iterate over all keywords for all moods/stages, performing substring searches. With ~80 keywords in `_MOOD_KEYWORDS` and ~30 in `_STAGE_KEYWORDS`, this is ~110 substring searches per user turn. Each `kw in lower` is O(n*m) for string length n and keyword length m.

**Current performance:** ~0.05-0.1ms per call. Not a bottleneck at all, but could be optimized if keyword lists grow.

**Optimization (only if needed):** Pre-compile into a regex pattern per mood:
```python
import re
_MOOD_PATTERNS = {
    mood: re.compile("|".join(re.escape(kw) for kw in keywords))
    for mood, keywords in _MOOD_KEYWORDS.items()
}
```

**Estimated improvement:** Negligible for current keyword counts. Only relevant if keyword lists grow to 500+.

---

### PERF-16: Healthcheck Uses Python Import for Agent Container (LOW)

| Field | Value |
|-------|-------|
| **Category** | BUILD / CPU |
| **Impact** | LOW (runs every 30s) |
| **Location** | `Dockerfile:22-23` |

**Description:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import socket; ..." || exit 1
```
Starting a Python interpreter every 30 seconds for a health check adds ~200ms of startup time and ~20MB of transient memory. The `python` command may also not be in PATH if using `uv`'s virtual env.

**Optimization — Use a lightweight alternative:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD timeout 2 bash -c '</dev/tcp/localhost/7880' || exit 1
```

Or install `curl` in the slim image:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:7880/ || exit 1
```

**Estimated improvement:** Reduces healthcheck resource usage by ~90%. Prevents potential `python` not-found errors.

---

## Memory Leak Risk Assessment

| Component | Risk | Growth Rate | Max Lifetime | Mitigation |
|-----------|------|-------------|-------------|------------|
| `CallMetrics.mood_history` | MEDIUM | ~2/min (1 per user turn) | Per-call (cleared between calls) | Cap with `deque(maxlen=100)` |
| `CallMetrics.response_times` | MEDIUM | ~1/min | Per-call | Cap with `deque(maxlen=50)` |
| `AurusVoiceAgent._transcript` | LOW | ~4/min | Per-call (reset in `entrypoint`) | Already bounded by call duration |
| Frontend `moodHistory` state | MEDIUM | ~2/min | Until disconnect (cleared) | Cap at 100 entries |
| Frontend `transcript` state | MEDIUM | ~4/min, possibly 8/min with duplicates | Until disconnect | Cap at 200 entries, fix duplicates |
| `<audio>` DOM elements | LOW-MEDIUM | ~1 per reconnect | Until page reload | Clean up in `disconnect()` |
| `conversation_store` files | LOW | ~1 per call (disk) | Forever | Implement rotation/archival |
| VAD model copies from PERF-01 | HIGH | ~2MB per emotion change | GC-dependent | Fix PERF-01 (cache VAD) |

---

## Optimization Roadmap (Prioritized)

| Priority | Finding | Effort | Impact | Category |
|----------|---------|--------|--------|----------|
| **P0** | PERF-01: Cache VAD/STT/LLM in `_build_agent()` | 2h | HIGH — saves 120-250ms per emotion change | LATENCY |
| **P0** | PERF-03: Reduce `min_endpointing_delay` to 0.3 | 5m | HIGH — saves 200ms per turn | LATENCY |
| **P1** | PERF-07: Cap frontend state arrays | 30m | MEDIUM — prevents unbounded memory | MEMORY |
| **P1** | PERF-06: Fix audio element cleanup | 15m | MEDIUM — prevents DOM leaks | MEMORY |
| **P1** | PERF-14: Fix duplicate transcript entries | 30m | LOW-MEDIUM — cleaner data | MEMORY |
| **P2** | PERF-02: Cap `CallMetrics` lists with deque | 15m | MEDIUM — prevents backend memory growth | MEMORY |
| **P2** | PERF-04: Async file I/O in ConversationStore | 30m | MEDIUM — prevents event loop blocking | LATENCY |
| **P2** | PERF-12: Docker standalone output | 1h | MEDIUM — faster deploys | BUILD |
| **P3** | PERF-08: Fix useCallback dependency arrays | 15m | LOW — fewer re-renders | CPU |
| **P3** | PERF-09: Fix keyboard handler dependencies | 10m | LOW — fewer listener re-attachments | CPU |
| **P3** | PERF-10: Throttle idle AudioVisualizer | 20m | LOW-MEDIUM — battery savings | CPU |
| **P3** | PERF-05: Lazy conversation loading | 1h | MEDIUM — scales with history | MEMORY |
| **P4** | PERF-11: Reuse OpenAI client for summary | 5m | LOW | LATENCY |
| **P4** | PERF-13: Clear stale state between calls | 10m | LOW | MEMORY |
| **P4** | PERF-16: Lightweight Docker healthcheck | 10m | LOW | BUILD |

---

## Summary of Potential Latency Savings

Implementing P0 optimizations alone:

```
BEFORE:
  VAD endpointing:       500ms
  Agent reconstruction:  120-250ms  (when mood changes)
                         ─────────
  Controllable latency:  620-750ms

AFTER:
  VAD endpointing:       300ms  (reduced from 500)
  Agent reconstruction:  ~5ms   (cached components)
                         ────────
  Controllable latency:  305ms

  Savings: 315-445ms per response turn
```

With fillers masking the LLM inference time, the **perceived latency** drops from ~500ms to ~300ms, well within the sub-500ms target.
