# Aurus Voice Agent - Project Rules

## Project Overview
Competition voice agent ("Everlast" team) — a German-speaking AI phone agent with persona routing, emotion engine, and latency masking. Goal: sub-500ms response latency.

## Architecture
- **Monorepo:** `/agent` (Python 3.12) + `/frontend` (Next.js 15)
- **Transport:** LiveKit WebRTC — NO WebSockets for audio
- **LLM:** OpenAI GPT-4o (structured JSON output)
- **STT:** Deepgram Nova-3 (German, streaming)
- **TTS:** Cartesia Sonic (German, emotion control)
- **Deploy:** Docker Compose (Hetzner VPS)

## Code Standards

### Python (`/agent`)
- Python 3.12+, managed with `uv`
- Always use `async/await` — no blocking calls
- Type hints on all function signatures
- Use `pydantic` for data models and config validation
- Logging via `structlog` — no print statements
- Format with `ruff format`, lint with `ruff check`

### TypeScript (`/frontend`)
- Next.js 15 App Router — no Pages Router
- Tailwind CSS + shadcn/ui components
- Strict TypeScript — no `any` types
- Use server components by default, `"use client"` only when needed
- Format with `prettier`, lint with `eslint`

## Key Rules
1. **No Hallucinations:** Never invent API methods. Verify against docs.
2. **Latency First:** Every design decision optimizes for time-to-first-byte.
3. **German Speech, English Code:** Bot speaks German. All code, comments, variable names in English.
4. **Structured LLM Output:** GPT-4o always returns JSON with `response_text`, `detected_user_mood`, `required_tone`, `action`.
5. **Filler Injection:** Play cached German fillers ("Hmm", "Ja", "Verstehe") immediately on VAD end-of-speech to mask LLM latency.
