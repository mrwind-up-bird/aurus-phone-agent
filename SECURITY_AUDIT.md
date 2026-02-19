# Aurus Voice Agent -- Security Audit Report

**Date:** 2026-02-19
**Auditor:** Automated Security Review (Claude)
**Scope:** Full codebase -- agent backend, frontend API routes, infrastructure, client-side code
**Commit:** `29ae921` (main branch)

---

## Executive Summary

The Aurus Voice Agent is a competition prototype with a moderate attack surface. The primary risks stem from **unauthenticated API endpoints**, **lack of input validation on data channels**, **plaintext conversation storage**, and **Docker containers running as root**. While some findings are mitigated by the internal/demo nature of the application, several issues would become critical in a production deployment.

**Finding Summary:**
| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 5     |
| MEDIUM   | 6     |
| LOW      | 4     |
| INFO     | 3     |

---

## Findings

### SEC-01: Unauthenticated Token Endpoint Enables Room Hijacking

| Field | Value |
|-------|-------|
| **ID** | SEC-01 |
| **Severity** | CRITICAL |
| **OWASP** | A01:2021 -- Broken Access Control |
| **Location** | `frontend/src/app/api/token/route.ts:11-69` |

**Description:**
The `/api/token` POST endpoint generates LiveKit access tokens with full publish/subscribe/data permissions for any caller. There is no authentication, no rate limiting, no CORS restriction, and no origin validation. An attacker can call this endpoint with arbitrary `roomName` and `participantName` values to:
1. Join any active call and eavesdrop on conversations
2. Inject data channel messages to trigger persona switches or tone shifts
3. Flood the system by creating unlimited rooms and dispatching agents

**Vulnerable Code:**
```typescript
// frontend/src/app/api/token/route.ts:11-12
export async function POST(req: NextRequest) {
  const { roomName, participantName, metadata } = await req.json();
  // No authentication check -- anyone can request a token
```

```typescript
// frontend/src/app/api/token/route.ts:58-64
token.addGrant({
  roomJoin: true,
  room: roomName,
  canPublish: true,
  canSubscribe: true,
  canPublishData: true,  // Allows sending arbitrary data channel messages
});
```

**Recommendation:**
1. Add authentication middleware (session cookie, API key, or JWT) to the token endpoint
2. Implement rate limiting (e.g., 5 requests per minute per IP)
3. Restrict `canPublishData: true` to operator/admin tokens only -- regular call participants should not be able to send data channel commands
4. Validate `roomName` against an allowlist or pattern (e.g., `^[a-z0-9-]{3,50}$`)
5. Add CORS headers to restrict requests to the frontend origin

```typescript
// Recommended: Add authentication and validation
export async function POST(req: NextRequest) {
  // 1. Authenticate the request
  const session = await getServerSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { roomName, participantName, metadata } = await req.json();

  // 2. Validate inputs
  if (!/^[a-z0-9-]{3,50}$/.test(roomName)) {
    return NextResponse.json({ error: "Invalid room name" }, { status: 400 });
  }

  // 3. Restrict permissions for non-admin users
  token.addGrant({
    roomJoin: true,
    room: roomName,
    canPublish: true,
    canSubscribe: true,
    canPublishData: session.role === "operator",
  });
  // ...
}
```

---

### SEC-02: Unauthenticated Conversation History API Exposes PII

| Field | Value |
|-------|-------|
| **ID** | SEC-02 |
| **Severity** | HIGH |
| **OWASP** | A01:2021 -- Broken Access Control |
| **Location** | `frontend/src/app/api/conversations/route.ts:44-90`, `frontend/src/app/api/conversations/[id]/route.ts:47-111` |

**Description:**
Both conversation API routes (`GET /api/conversations` and `GET /api/conversations/:id`) have zero authentication. Anyone who can reach the server can enumerate all conversations, read full transcripts, and access lead PII (names, companies, job titles, phone numbers, gender). This data is protected under GDPR/DSGVO in Germany.

**Vulnerable Code:**
```typescript
// frontend/src/app/api/conversations/route.ts:44
export async function GET(): Promise<NextResponse> {
  // No authentication -- returns all conversation data to any caller
```

**Recommendation:**
1. Add authentication middleware to both routes
2. Implement pagination to prevent bulk data exfiltration
3. Consider field-level access control (e.g., redact phone numbers for non-admin users)
4. Add audit logging for data access

---

### SEC-03: Data Channel Messages Accepted Without Validation or Authentication

| Field | Value |
|-------|-------|
| **ID** | SEC-03 |
| **Severity** | HIGH |
| **OWASP** | A03:2021 -- Injection |
| **Location** | `agent/src/agent.py:574-592` |

**Description:**
The `on_data_received` handler parses JSON from the LiveKit data channel without any schema validation, sender verification, or rate limiting. Any participant in the room can send `persona_switch` or `tone_shift` commands to manipulate the agent's behavior mid-call. The `persona` key from the message is passed directly to `_handle_persona_switch()` without validation against known persona keys (only caught later by a `KeyError` in the persona manager).

**Vulnerable Code:**
```python
# agent/src/agent.py:574-592
@ctx.room.on("data_received")
def on_data_received(data: rtc.DataPacket) -> None:
    try:
        msg = json.loads(data.data.decode())
        if msg.get("type") == "persona_switch":
            new_persona_key = msg.get("persona")  # No validation
            if new_persona_key and self._tonality_mapper and self._session:
                loop.create_task(
                    self._handle_persona_switch(new_persona_key)
                )
        elif msg.get("type") == "tone_shift":
            tone_str = msg.get("tone")  # No validation
            # ...
    except (json.JSONDecodeError, KeyError):
        pass  # Silent failure hides attacks
```

**Recommendation:**
1. Verify the sender's identity -- only accept commands from operator/dashboard participants, not from the call lead
2. Validate `persona` against `self._persona_manager.list_personas()` before processing
3. Validate `tone_str` against known `RequiredTone` values (already partially done via `RequiredTone(tone_str)`)
4. Add structured logging for rejected messages (audit trail)
5. Define a Pydantic model for incoming data channel messages

```python
# Recommended: Validate sender and payload
@ctx.room.on("data_received")
def on_data_received(data: rtc.DataPacket) -> None:
    # Only accept commands from dashboard operators, not leads
    if not data.participant or not data.participant.identity.startswith("dashboard-"):
        return

    try:
        msg = json.loads(data.data.decode())
    except json.JSONDecodeError:
        logger.warning("invalid_data_channel_message", participant=data.participant.identity)
        return

    if msg.get("type") == "persona_switch":
        new_persona_key = msg.get("persona")
        if new_persona_key in self._persona_manager.list_personas():
            loop.create_task(self._handle_persona_switch(new_persona_key))
        else:
            logger.warning("unknown_persona_requested", key=new_persona_key)
```

---

### SEC-04: Conversation Data Stored as Plaintext JSON on Disk

| Field | Value |
|-------|-------|
| **ID** | SEC-04 |
| **Severity** | HIGH |
| **OWASP** | A02:2021 -- Cryptographic Failures |
| **Location** | `agent/src/conversation_store.py:93-111` |

**Description:**
Conversation records -- including full transcripts, lead names, companies, phone numbers, and AI-generated summaries -- are persisted as unencrypted JSON files on disk. The files are readable by any process running on the host. In the Docker Compose setup, the conversation volume is shared between the agent and frontend containers, expanding the blast radius. Under GDPR/DSGVO, call recordings and personal data must be protected with appropriate technical measures.

**Vulnerable Code:**
```python
# agent/src/conversation_store.py:104
filepath.write_text(record.model_dump_json(indent=2), encoding="utf-8")
```

**Recommendation:**
1. Encrypt conversation files at rest using `cryptography.fernet` or similar
2. Store encryption keys in a secrets manager, not in environment variables
3. Implement automatic data retention and deletion policies (e.g., purge after 30 days)
4. Add file permissions restrictions (`chmod 600` on conversation files)
5. Consider using a database with built-in encryption instead of flat files

---

### SEC-05: Docker Containers Run as Root

| Field | Value |
|-------|-------|
| **ID** | SEC-05 |
| **Severity** | HIGH |
| **OWASP** | A05:2021 -- Security Misconfiguration |
| **Location** | `Dockerfile:1-25` (agent stage), `Dockerfile:42-57` (frontend stage) |

**Description:**
Both the agent and frontend Docker containers run as root. If an attacker achieves code execution through any vulnerability (e.g., dependency supply chain attack, SSRF), they gain root access inside the container, which significantly increases the potential for container escape and lateral movement.

**Vulnerable Code:**
```dockerfile
# Dockerfile:1-25 -- No USER directive; defaults to root
FROM python:3.12-slim AS agent
WORKDIR /app/agent
# ... no USER directive anywhere
CMD ["uv", "run", "python", "-m", "src.agent"]

# Dockerfile:42-57 -- Same issue
FROM node:22-slim AS frontend
# ... no USER directive
CMD ["npm", "start"]
```

**Recommendation:**
```dockerfile
# Agent stage -- add non-root user
FROM python:3.12-slim AS agent
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser
WORKDIR /app/agent
# ... (install dependencies)
RUN chown -R appuser:appuser /app
USER appuser
CMD ["uv", "run", "python", "-m", "src.agent"]

# Frontend stage -- add non-root user
FROM node:22-slim AS frontend
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser
WORKDIR /app/frontend
# ... (copy build artifacts)
RUN chown -R appuser:appuser /app
USER appuser
CMD ["npm", "start"]
```

---

### SEC-06: Potential Path Traversal in Conversation Filename Generation

| Field | Value |
|-------|-------|
| **ID** | SEC-06 |
| **Severity** | HIGH |
| **OWASP** | A03:2021 -- Injection |
| **Location** | `agent/src/conversation_store.py:40-45`, `agent/src/conversation_store.py:79-91` |

**Description:**
The `_slugify()` function removes non-word characters from the lead name, but the result is concatenated into a file path without verifying it doesn't escape the base directory. While `_slugify` does strip most dangerous characters, the `re.sub(r"[^\w\s-]", "", text)` pattern preserves underscores and hyphens. More importantly, `_build_filename` uses `lead_metadata.get("name", "unknown")` which comes from room metadata controlled by the client (via the token API). A carefully crafted name containing sequences like `..` after slugification could theoretically be used in conjunction with other bugs.

However, since `\w` does not match `/` or `.` in Python's default regex mode, and the `_slugify` function strips these characters, the actual exploitability is **low in the current implementation**. The risk is elevated because:
1. The slug is used in a path concatenation (`self._base_dir / filename`)
2. There is no explicit path traversal check (e.g., `resolve()` validation)

**Vulnerable Code:**
```python
# agent/src/conversation_store.py:40-45
def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)  # Keeps \w (letters, digits, underscore) and hyphens
    text = re.sub(r"[\s_]+", "_", text)
    return text.strip("_") or "unknown"

# agent/src/conversation_store.py:101-102
filename = self._build_filename(record)
filepath = self._base_dir / filename  # No traversal check
```

**Recommendation:**
Add an explicit path containment check after constructing the filepath:

```python
async def save(self, record: ConversationRecord) -> Path:
    filename = self._build_filename(record)
    filepath = (self._base_dir / filename).resolve()

    # Ensure the resolved path is still within the base directory
    if not filepath.is_relative_to(self._base_dir.resolve()):
        raise ValueError(f"Path traversal detected: {filename}")

    filepath.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return filepath
```

---

### SEC-07: No Security Headers in Next.js Configuration

| Field | Value |
|-------|-------|
| **ID** | SEC-07 |
| **Severity** | MEDIUM |
| **OWASP** | A05:2021 -- Security Misconfiguration |
| **Location** | `frontend/next.config.ts:1-7` |

**Description:**
The Next.js configuration is empty -- no security headers are set. The application is missing:
- `Content-Security-Policy` (CSP)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Strict-Transport-Security` (HSTS)
- `Referrer-Policy`
- `Permissions-Policy`

This leaves the application vulnerable to clickjacking, MIME sniffing, and other browser-based attacks.

**Vulnerable Code:**
```typescript
// frontend/next.config.ts
const nextConfig: NextConfig = {
  /* config options here */  // Empty -- no security headers
};
```

**Recommendation:**
```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-XSS-Protection", value: "0" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=()" },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              "connect-src 'self' wss://*.livekit.cloud",
              "media-src 'self' blob:",
              "img-src 'self' data:",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
```

---

### SEC-08: Frontend Renders Transcript Text Without Sanitization

| Field | Value |
|-------|-------|
| **ID** | SEC-08 |
| **Severity** | MEDIUM |
| **OWASP** | A03:2021 -- Injection |
| **Location** | `frontend/src/components/transcript-view.tsx:78` |

**Description:**
Transcript text received from the data channel is rendered directly in JSX. While React automatically escapes string interpolation in JSX (preventing most XSS), the text originates from user speech (via STT) and agent responses (via LLM). If the application were ever to use `dangerouslySetInnerHTML` or render these values in attributes, it would be exploitable.

Current risk is **low** because React's JSX escaping provides protection. However, the data flow is:
1. User speaks -> Deepgram STT transcription -> data channel -> frontend state -> DOM

The STT output is generally safe, but:
- The `conversation-history.tsx:473-480` component renders lead metadata keys and values directly, which are client-controlled
- The `conversation-history.tsx:357` component renders summary text from the AI

**Relevant Code:**
```tsx
// frontend/src/components/transcript-view.tsx:78
{entry.text}  // React auto-escapes this -- currently safe

// frontend/src/components/conversation-history.tsx:473-479
{Object.entries(conversation.lead_metadata).map(([key, value]) => (
  <span key={key}>
    <span>{key}:</span> {value}  // Client-controlled metadata rendered
  </span>
))}
```

**Recommendation:**
1. The current implementation is safe due to React's escaping. Maintain this by never using `dangerouslySetInnerHTML` with user-provided content.
2. Consider adding a Content-Security-Policy header (SEC-07) as defense-in-depth.
3. Add input length limits on metadata values in the token endpoint to prevent DOM flooding.

---

### SEC-09: Regex Patterns Loaded from YAML Configuration

| Field | Value |
|-------|-------|
| **ID** | SEC-09 |
| **Severity** | MEDIUM |
| **OWASP** | A03:2021 -- Injection |
| **Location** | `agent/src/persona_manager.py:56` |

**Description:**
The persona routing logic uses `re.search()` with regex patterns loaded from `personas.yaml`. While YAML is loaded using `yaml.safe_load()` (preventing YAML deserialization attacks), the regex patterns in the file are used directly in `re.search()`. If an attacker could modify the YAML file (e.g., via compromised CI/CD or supply chain attack), they could inject a ReDoS (Regular Expression Denial of Service) pattern that causes catastrophic backtracking.

Current patterns are simple alternations (e.g., `"CTO|VP Engineering|Tech Lead"`) and are not vulnerable.

**Vulnerable Code:**
```python
# agent/src/persona_manager.py:56
if re.search(rule["pattern"], lead.job_title, re.IGNORECASE):
```

**Recommendation:**
1. Validate regex patterns at load time -- reject patterns with nested quantifiers
2. Use `re.compile()` with a timeout or use the `regex` library with `timeout` parameter
3. Add a maximum length check on `lead.job_title` before regex matching

```python
# Recommended: Pre-compile and validate patterns
import re

def _load_config(self) -> None:
    raw = yaml.safe_load(self._config_path.read_text())
    # ...
    for rule in raw.get("routing", {}).get("title_matching", []):
        try:
            rule["_compiled"] = re.compile(rule["pattern"], re.IGNORECASE)
        except re.error as e:
            logger.error("invalid_regex_pattern", pattern=rule["pattern"], error=str(e))
            raise
```

---

### SEC-10: Docker Compose Lacks Resource Limits and Security Options

| Field | Value |
|-------|-------|
| **ID** | SEC-10 |
| **Severity** | MEDIUM |
| **OWASP** | A05:2021 -- Security Misconfiguration |
| **Location** | `docker-compose.yml:1-36` |

**Description:**
The Docker Compose file has no resource limits (memory, CPU), no read-only filesystem, no capability dropping, and no security options. This means:
1. A runaway process (e.g., infinite loop, memory leak) can exhaust host resources
2. A compromised container has unnecessary Linux capabilities
3. The container filesystem is writable, enabling persistence by attackers

**Vulnerable Code:**
```yaml
# docker-compose.yml -- no resource limits or security hardening
services:
  agent:
    build:
      context: .
      target: agent
    env_file: .env
    # Missing: deploy.resources, security_opt, read_only, tmpfs, cap_drop
```

**Recommendation:**
```yaml
services:
  agent:
    build:
      context: .
      dockerfile: Dockerfile
      target: agent
    env_file: .env
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    networks:
      - aurus
    volumes:
      - conversation-data:/app/agent/data/conversations

  frontend:
    build:
      context: .
      dockerfile: Dockerfile
      target: frontend
    env_file: .env
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "0.5"
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    read_only: true
    tmpfs:
      - /tmp
    ports:
      - "3000:3000"
    networks:
      - aurus
```

---

### SEC-11: Frontend Healthcheck Uses curl (Not Installed in Slim Image)

| Field | Value |
|-------|-------|
| **ID** | SEC-11 |
| **Severity** | MEDIUM |
| **OWASP** | A05:2021 -- Security Misconfiguration |
| **Location** | `Dockerfile:53-54` |

**Description:**
The frontend container uses `curl` in its healthcheck, but `node:22-slim` does not include `curl`. This means the healthcheck will always fail, and Docker/orchestrators may repeatedly restart the container. Installing `curl` in the image to fix this would increase the attack surface unnecessarily.

**Vulnerable Code:**
```dockerfile
# Dockerfile:53-54
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:3000/ || exit 1
```

**Recommendation:**
Use Node.js for the healthcheck instead:
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD node -e "const http = require('http'); http.get('http://localhost:3000/', (r) => { process.exit(r.statusCode === 200 ? 0 : 1); }).on('error', () => process.exit(1));"
```

---

### SEC-12: LiveKit API Secret Exposed to Frontend Container

| Field | Value |
|-------|-------|
| **ID** | SEC-12 |
| **Severity** | MEDIUM |
| **OWASP** | A02:2021 -- Cryptographic Failures |
| **Location** | `docker-compose.yml:18`, `frontend/.env.example:5-6` |

**Description:**
The Docker Compose file passes the full `.env` file (including `LIVEKIT_API_SECRET`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`) to both containers via `env_file: .env`. The frontend container only needs `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `NEXT_PUBLIC_LIVEKIT_URL`, but receives all secrets. If the frontend container is compromised, the attacker gets access to all API keys.

**Recommendation:**
1. Create separate `.env` files for each service (`.env.agent`, `.env.frontend`)
2. Use Docker secrets for sensitive values instead of environment variables
3. At minimum, split the env file:

```yaml
services:
  agent:
    env_file: .env.agent  # LIVEKIT_*, OPENAI_*, DEEPGRAM_*, CARTESIA_*

  frontend:
    env_file: .env.frontend  # Only LIVEKIT_API_KEY, LIVEKIT_API_SECRET, NEXT_PUBLIC_LIVEKIT_URL
```

---

### SEC-13: Sensitive Data Potentially Logged via structlog

| Field | Value |
|-------|-------|
| **ID** | SEC-13 |
| **Severity** | LOW |
| **OWASP** | A09:2021 -- Security Logging and Monitoring Failures |
| **Location** | `agent/src/agent.py:548`, `agent/src/agent.py:477-481` |

**Description:**
Several structlog calls include user speech transcripts and lead metadata in log output. In a production environment, these logs could leak PII to log aggregation services.

**Relevant Code:**
```python
# agent/src/agent.py:548
logger.info("user_speech", text=event.transcript, mood=detected_mood.value)

# agent/src/agent.py:477
logger.info("agent_starting", lead=lead.name, persona=persona.name, room=ctx.room.name)

# agent/src/agent.py:624
logger.info("agent_session_started", persona=persona.name, greeting=greeting)
```

**Recommendation:**
1. Configure structlog with a PII filter processor that redacts sensitive fields
2. Reduce log verbosity for transcript content (log at DEBUG level, truncate text)
3. Never log full greeting text (contains lead names)

```python
# Recommended: Truncate and redact
logger.info("user_speech", text_length=len(event.transcript), mood=detected_mood.value)
logger.debug("user_speech_detail", text=event.transcript[:50] + "...")
```

---

### SEC-14: OpenAI Client Instantiated Inside Function Scope

| Field | Value |
|-------|-------|
| **ID** | SEC-14 |
| **Severity** | LOW |
| **OWASP** | A06:2021 -- Vulnerable and Outdated Components |
| **Location** | `agent/src/agent.py:365-366` |

**Description:**
The `AsyncOpenAI` client is imported and instantiated inside `_generate_ai_summary()` on every call. While this is not a direct security vulnerability, it means:
1. The `OPENAI_API_KEY` is read from the environment on every summary generation
2. Connection pooling is not reused across calls
3. The inline import pattern (`from openai import AsyncOpenAI`) is unusual and makes dependency auditing harder

**Vulnerable Code:**
```python
# agent/src/agent.py:365-366
from openai import AsyncOpenAI
client = AsyncOpenAI()  # Reads OPENAI_API_KEY from env on every call
```

**Recommendation:**
Move the import to the top of the file and instantiate the client once:

```python
# At module level
from openai import AsyncOpenAI
_openai_client = AsyncOpenAI()

# In the method
async def _generate_ai_summary(self, transcript: list[TranscriptItem]) -> str:
    response = await _openai_client.chat.completions.create(...)
```

---

### SEC-15: No CSRF Protection on API Routes

| Field | Value |
|-------|-------|
| **ID** | SEC-15 |
| **Severity** | LOW |
| **OWASP** | A01:2021 -- Broken Access Control |
| **Location** | `frontend/src/app/api/token/route.ts`, `frontend/src/app/api/conversations/route.ts` |

**Description:**
The API routes have no CSRF protection. While the token endpoint requires a POST with JSON body (which provides some CSRF protection due to CORS preflight for `Content-Type: application/json`), there is no explicit CSRF token validation. The GET conversation endpoints are vulnerable to cross-site data leakage if authentication is added later without CSRF consideration.

**Recommendation:**
1. Add a custom header check (e.g., require `X-Requested-With: XMLHttpRequest`)
2. When adding authentication, implement proper CSRF tokens using Next.js middleware
3. Set `SameSite=Strict` on any session cookies

---

### SEC-16: Audio Element DOM Injection

| Field | Value |
|-------|-------|
| **ID** | SEC-16 |
| **Severity** | LOW |
| **OWASP** | A03:2021 -- Injection |
| **Location** | `frontend/src/hooks/use-agent-connection.ts:119-123` |

**Description:**
When a remote audio track is subscribed, the code creates an `<audio>` element and appends it to `document.body` with an ID derived from the participant's identity. While the `participant.identity` value comes from the LiveKit server (not directly from user input), a manipulated identity could potentially cause DOM ID collisions or be used for CSS-based attacks.

**Relevant Code:**
```typescript
// frontend/src/hooks/use-agent-connection.ts:119-123
const audioEl = document.createElement("audio");
audioEl.srcObject = stream;
audioEl.autoplay = true;
audioEl.id = `agent-audio-${participant.identity}`;  // Identity from server
document.body.appendChild(audioEl);
```

**Recommendation:**
1. Sanitize the participant identity before using it as a DOM ID
2. Use a generated UUID instead of the participant identity for the element ID
3. Track created elements in a ref and clean up properly on disconnect

---

### SEC-17: Conversation ID Enumeration in Detail Endpoint

| Field | Value |
|-------|-------|
| **ID** | SEC-17 |
| **Severity** | INFO |
| **OWASP** | A01:2021 -- Broken Access Control |
| **Location** | `frontend/src/app/api/conversations/[id]/route.ts:47-111` |

**Description:**
Conversation IDs are 12-character hex strings generated from `uuid.uuid4().hex[:12]`. While this provides reasonable entropy (~48 bits), the lack of authentication (SEC-02) means an attacker could attempt to brute-force or enumerate IDs. The endpoint iterates over all JSON files on disk for each request, making it susceptible to timing-based enumeration.

**Recommendation:**
This issue is fully mitigated by fixing SEC-02 (adding authentication). Additionally, consider using full UUIDs instead of truncated ones.

---

### SEC-18: Broad Exception Handling Masks Errors

| Field | Value |
|-------|-------|
| **ID** | SEC-18 |
| **Severity** | INFO |
| **OWASP** | A09:2021 -- Security Logging and Monitoring Failures |
| **Location** | `agent/src/agent.py:574-592`, `agent/src/agent.py:632` |

**Description:**
Several exception handlers use broad `except` clauses that silently swallow errors. This can mask security-relevant failures such as malformed input, authentication errors, or unexpected system states.

**Relevant Code:**
```python
# agent/src/agent.py:591-592
except (json.JSONDecodeError, KeyError):
    pass  # Silent -- no logging of invalid messages

# agent/src/agent.py:632
except (json.JSONDecodeError, Exception) as e:
    logger.warning("lead_metadata_parse_failed", error=str(e))
```

**Recommendation:**
1. Log all rejected data channel messages at WARNING level
2. Use specific exception types instead of broad `Exception`
3. Add metrics/counters for rejected messages to detect attack patterns

---

### SEC-19: No Rate Limiting on Conversation API Endpoints

| Field | Value |
|-------|-------|
| **ID** | SEC-19 |
| **Severity** | INFO |
| **OWASP** | A04:2021 -- Insecure Design |
| **Location** | `frontend/src/app/api/conversations/route.ts`, `frontend/src/app/api/conversations/[id]/route.ts` |

**Description:**
The conversation list endpoint reads and parses all JSON files from disk on every request. With many stored conversations, this becomes an amplification vector -- a single HTTP request triggers potentially hundreds of file reads. There is no rate limiting, pagination, or caching.

**Recommendation:**
1. Add pagination (limit/offset query parameters)
2. Implement response caching with appropriate TTL
3. Add rate limiting via Next.js middleware or a reverse proxy

---

## OWASP Top 10 (2021) Coverage Matrix

| OWASP Category | Findings | Status |
|---|---|---|
| A01: Broken Access Control | SEC-01, SEC-02, SEC-15, SEC-17 | Reviewed |
| A02: Cryptographic Failures | SEC-04, SEC-12 | Reviewed |
| A03: Injection | SEC-03, SEC-06, SEC-08, SEC-09, SEC-16 | Reviewed |
| A04: Insecure Design | SEC-19 | Reviewed |
| A05: Security Misconfiguration | SEC-05, SEC-07, SEC-10, SEC-11 | Reviewed |
| A06: Vulnerable and Outdated Components | SEC-14 | Partial -- dependency CVE scan not performed |
| A07: Identification and Authentication Failures | Covered by SEC-01, SEC-02 | Reviewed |
| A08: Software and Data Integrity Failures | Not applicable (no CI/CD in scope) | N/A |
| A09: Security Logging and Monitoring Failures | SEC-13, SEC-18 | Reviewed |
| A10: Server-Side Request Forgery (SSRF) | No SSRF vectors identified | Clear |

---

## Remediation Priority Roadmap

### Phase 1: Immediate (Before Any Production Deployment)

| Priority | Finding | Effort |
|----------|---------|--------|
| 1 | SEC-01: Add authentication to token endpoint | Medium |
| 2 | SEC-02: Add authentication to conversation APIs | Medium |
| 3 | SEC-05: Add non-root USER to Dockerfiles | Low |
| 4 | SEC-12: Split env files per service | Low |

### Phase 2: Short-Term (Within 1-2 Weeks)

| Priority | Finding | Effort |
|----------|---------|--------|
| 5 | SEC-03: Validate data channel messages and check sender identity | Medium |
| 6 | SEC-07: Add security headers to Next.js config | Low |
| 7 | SEC-10: Add resource limits and security options to Docker Compose | Low |
| 8 | SEC-11: Fix frontend healthcheck (use Node.js instead of curl) | Low |
| 9 | SEC-06: Add path traversal check in conversation store | Low |

### Phase 3: Medium-Term (Within 1 Month)

| Priority | Finding | Effort |
|----------|---------|--------|
| 10 | SEC-04: Encrypt conversation data at rest | High |
| 11 | SEC-09: Pre-compile and validate YAML regex patterns | Low |
| 12 | SEC-13: Add PII filtering to structured logs | Medium |
| 13 | SEC-15: Add CSRF protection | Medium |
| 14 | SEC-19: Add pagination and rate limiting to APIs | Medium |

### Phase 4: Hardening (Ongoing)

| Priority | Finding | Effort |
|----------|---------|--------|
| 15 | SEC-14: Move OpenAI client to module scope | Low |
| 16 | SEC-16: Sanitize DOM element IDs | Low |
| 17 | SEC-17: Use full UUIDs for conversation IDs | Low |
| 18 | SEC-18: Improve exception handling and audit logging | Low |
| 19 | Run dependency CVE scan (`pip audit`, `npm audit`) | Low |

---

## Appendix: Files Reviewed

| File | Lines | Purpose |
|------|-------|---------|
| `agent/src/agent.py` | 651 | Main voice agent orchestration |
| `agent/src/models.py` | 80 | Pydantic data models |
| `agent/src/persona_manager.py` | 92 | YAML persona loading and routing |
| `agent/src/tonality_mapper.py` | 66 | TTS emotion mapping |
| `agent/src/call_metrics.py` | 187 | Real-time call analytics |
| `agent/src/conversation_store.py` | 156 | JSON file persistence |
| `agent/src/events.py` | 53 | Event models |
| `agent/src/filler_injection.py` | 76 | Filler audio management |
| `agent/personas.yaml` | 98 | Persona and routing configuration |
| `frontend/src/app/api/token/route.ts` | 69 | LiveKit token generation |
| `frontend/src/app/api/conversations/route.ts` | 91 | Conversation list API |
| `frontend/src/app/api/conversations/[id]/route.ts` | 112 | Conversation detail API |
| `frontend/src/hooks/use-agent-connection.ts` | 266 | LiveKit room connection |
| `frontend/src/hooks/use-conversations.ts` | 71 | Conversation data fetching |
| `frontend/src/app/page.tsx` | 353 | Dashboard page |
| `frontend/src/components/transcript-view.tsx` | 86 | Transcript rendering |
| `frontend/src/components/conversation-history.tsx` | 532 | Conversation history panel |
| `frontend/src/components/connection-panel.tsx` | 232 | Connection form |
| `frontend/src/components/sentiment-coaching.tsx` | 235 | Sentiment coaching UI |
| `frontend/src/components/sentiment-graph.tsx` | 274 | Sentiment visualization |
| `frontend/src/lib/types.ts` | 119 | TypeScript type definitions |
| `frontend/next.config.ts` | 7 | Next.js configuration |
| `Dockerfile` | 57 | Multi-stage Docker build |
| `docker-compose.yml` | 36 | Container orchestration |
| `.env.example` | 15 | Environment variable template |
| `.gitignore` | 36 | Git ignore rules |
