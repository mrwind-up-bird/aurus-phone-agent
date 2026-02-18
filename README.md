# Aurus Voice Agent

**Team Everlast** | AI Voice Agent Competition Entry

A German-speaking AI phone agent with smart persona routing, real-time emotion engine, and a glassmorphism monitoring dashboard.

## Architecture

```
                 Lead Metadata
                      |
                      v
              ┌───────────────┐
              │ Persona Router │ ── Title Match → Marcus (CTO)
              │   (YAML-based) │ ── Gender Balance → Sarah/Lukas
              └───────┬───────┘
                      │
        ┌─────────────┼─────────────┐
        v             v             v
   ┌─────────┐  ┌─────────┐  ┌─────────┐
   │  Lukas   │  │  Sarah   │  │ Marcus  │
   │ Closer   │  │ Empath   │  │ Techie  │
   │ Cartesia │  │ Cartesia │  │ Cartesia│
   └────┬─────┘  └────┬─────┘  └────┬────┘
        └──────────────┼─────────────┘
                       v
            ┌──────────────────┐
            │   Voice Pipeline  │
            │  STT → LLM → TTS │
            │  Deepgram  GPT-4o │
            │  Nova-3   Cartesia│
            └────────┬─────────┘
                     │ WebRTC
                     v
            ┌──────────────────┐
            │   LiveKit Cloud   │
            │  (Germany Region) │
            └────────┬─────────┘
                     │
                     v
            ┌──────────────────┐
            │    Dashboard UI   │
            │  Next.js + Glass  │
            └──────────────────┘
```

## Key Features

### Smart Persona Routing
Automatically selects the optimal AI persona based on lead metadata:
- **Lukas** (The Closer) — calm, authoritative → targets CEOs, CFOs
- **Sarah** (The Empath) — warm, enthusiastic → targets HR, Marketing
- **Marcus** (The Techie) — fast, direct → targets CTOs, Developers

Routing priority: Job title matching → Gender-based psychological balancing → Default fallback. Live persona switching during calls via the dashboard.

### Real-Time Emotion Engine
Detects user mood from German speech using keyword analysis (7 mood categories: neutral, interested, enthusiastic, skeptical, frustrated, confused, dismissive). Maps detected mood to optimal response tone and dynamically adjusts Cartesia TTS emotion parameters mid-call:

| User Mood     | Agent Tone    | TTS Emotions            |
|---------------|---------------|-------------------------|
| Interested    | Enthusiastic  | Enthusiastic, Excited   |
| Skeptical     | Reassuring    | Trust, Calm             |
| Frustrated    | Empathetic    | Sympathetic, Calm       |
| Enthusiastic  | Enthusiastic  | Enthusiastic, Confident |
| Confused      | Reassuring    | Trust, Calm             |
| Dismissive    | Empathetic    | Sympathetic, Affectionate|

### Proactive Cold Calling
The agent speaks first — no waiting for the user. Uses time-aware greetings ("Guten Morgen/Tag/Abend"), personalizes with lead name and Herr/Frau title, and mentions the company if known. This mirrors real sales agent behavior.

### Filler Injection (Latency Masking)
8 pre-recorded German filler phrases ("hmm", "genau", "verstehe", etc.) play automatically during LLM processing via LiveKit's BackgroundAudioPlayer. This creates natural conversation flow and masks the 200-400ms LLM thinking latency.

### Call Metrics & Lead Scoring
Real-time lead scoring (0-100) based on mood trajectory, engagement, conversation stage progression, and objection handling. Tracks 6 sales stages (Begrüßung → Qualifizierung → Pitch → Einwandbehandlung → Abschluss → Follow-Up) with automatic German keyword detection.

### AI-Powered Call Summaries
Every call ends with a GPT-4o-mini generated German summary covering outcome, lead mood, and next steps. A post-call overlay displays the result with lead score ring, duration, and mood trend.

### Conversation Persistence
Every call is automatically saved as a JSON record with full transcript, detected moods, persona used, and auto-generated summary. Browse and replay past conversations from the glassmorphism history panel.

### Glassmorphism Dashboard
Real-time monitoring dashboard with:
- **Audio Visualizer** — HiDPI canvas with per-bar gradients and glow effects
- **Sentiment Graph** — SVG bezier curves showing mood trajectory over time
- **Call Metrics Bar** — Live timer, lead score ring, response time, turns, stage indicator, mood trend
- **Persona Switcher** — Live hot-swap personas during active calls
- **Transcript View** — Glass bubbles with mood badges
- **Conversation History** — Slide-out panel with search and detail view
- **Post-Call Summary** — Overlay with AI-generated outcome analysis

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Transport | LiveKit WebRTC | Sub-200ms audio streaming |
| STT | Deepgram Nova-3 | German speech recognition |
| LLM | OpenAI GPT-4o | Conversation intelligence |
| TTS | Cartesia Sonic | German voice synthesis + emotion control |
| VAD | Silero | Voice activity detection |
| Backend | Python 3.12 + uv | Agent orchestration |
| Frontend | Next.js 16 + Tailwind v4 | Dashboard UI |
| Deployment | Docker + Hetzner | Germany-hosted infra |

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 22+
- API keys: LiveKit, OpenAI, Deepgram, Cartesia

### Agent
```bash
cd agent
cp ../.env.example .env  # Add your API keys
uv sync
uv run python -m src.agent dev
```

### Frontend
```bash
cd frontend
cp .env.example .env.local  # Add LiveKit credentials
npm install
npm run dev
```

Open `http://localhost:3003` — fill in lead details and click "Anruf starten".

## Project Structure

```
aurus-phone-agent/
├── agent/
│   ├── src/
│   │   ├── agent.py              # Main LiveKit agent + emotion engine
│   │   ├── persona_manager.py    # YAML-based persona routing
│   │   ├── tonality_mapper.py    # Mood → Cartesia emotion mapping
│   │   ├── conversation_store.py # JSON persistence layer
│   │   ├── filler_injection.py   # Latency masking (cached WAVs)
│   │   ├── models.py             # Pydantic models
│   │   └── events.py             # Event models
│   ├── personas.yaml             # 3 persona definitions + routing rules
│   ├── assets/fillers/           # 8 German filler audio files
│   └── data/conversations/       # Saved conversation records
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # Dashboard layout
│   │   │   └── api/              # Token + conversations API
│   │   ├── components/           # Glassmorphism UI components
│   │   ├── hooks/                # LiveKit + data hooks
│   │   └── lib/types.ts          # Shared TypeScript types
│   └── ...
├── Dockerfile                    # Multi-stage build
├── docker-compose.yml            # Production deployment
└── CLAUDE.md                     # Project conventions
```

## How It Works

1. **Lead connects** → Frontend requests token from `/api/token`
2. **Room created** → LiveKit room with lead metadata, agent dispatched
3. **Persona selected** → Router analyzes job title/gender, picks optimal persona
4. **Call begins** → STT → LLM → TTS pipeline streams audio via WebRTC
5. **Emotion detected** → Each user utterance analyzed for mood keywords
6. **TTS adapts** → Agent dynamically shifts voice emotion parameters
7. **Dashboard updates** → Sentiment graph, transcript, and state indicators update in real-time
8. **Call ends** → Conversation auto-saved with full transcript and mood history

---

Built with care by **Team Everlast** for the AI Voice Agent Competition.
