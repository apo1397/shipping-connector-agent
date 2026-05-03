# GoKwik Shipping Connector Agent — Architecture

## What it does

Takes a shipping provider's API documentation URL, runs it through an LLM pipeline, and produces an exhaustive JSON config file that a developer or coding agent can use to implement the connector without any guesswork.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| LLM | Anthropic / Gemini / any OpenAI-compatible API (Groq, NVIDIA, etc.) |
| LLM abstraction | LangChain |
| HTTP client | httpx (async) |
| HTML scraping | BeautifulSoup4 + html2text |
| Real-time updates | Server-Sent Events (SSE) via sse-starlette |
| Frontend | Vanilla JS + Tailwind CSS |

---

## Directory Layout

```
backend/
  api/          → HTTP routes + Pydantic request/response schemas
  agent/        → Orchestrator (pipeline driver) + AgentContext (session state)
  analyzer/     → LLM client + API discovery + status extractor
  fetcher/      → URL fetcher + HTML→markdown converter
  generator/    → Config assembler (no LLM — pure data assembly)
  tester/       → E2E endpoint tester (live HTTP calls with real credentials)
  models/       → Shared Pydantic models

frontend/
  index.html    → 5-step wizard
  app.js        → SSE listener + step navigation + UI rendering
  style.css     → Custom styles on top of Tailwind
```

---

## The Pipeline (5 Steps)

Every analysis run goes through this pipeline, driven by `AgentOrchestrator.run()`. Progress is streamed to the browser over SSE in real time.

```
Step 1 — FETCH
  FetcherDetector downloads the URL.
  If HTML → BeautifulSoup extracts <article>/<main>, html2text converts to markdown.
  If Postman JSON → parsed directly.
  Output: clean markdown text (~10–20k chars).

Step 2 — DISCOVER APIs  [1 LLM call each]
  LLM #1: Find the tracking endpoint.
    Returns: method, full URL, AWB location (path/query/body), AWB field name,
             response field paths, body-level error detection fields, rate limit info.
    If multiple endpoints found (B2C vs B2B etc.):
      → emits clarification_needed SSE event
      → [PAUSE 1] waits for user to pick one
      → re-runs with a focus hint
  LLM #2: Find the auth mechanism.
    Returns: type (api_key_header / login_flow / basic / oauth2 / none),
             credentials required, inject header + format, "how to get creds" guide.

Step 3 — EXTRACT STATUSES  [1 LLM call]
  LLM reads the docs and extracts every provider status code with description + is_terminal flag.

Step 4 — SUGGEST MAPPINGS  [1 LLM call]
  LLM maps each provider status to the closest canonical GoKwik status.
  → emits mapping_review SSE event
  → [PAUSE 2] waits for user to confirm/adjust mappings in the UI table

Step 5 — GENERATE CONFIG  [0 LLM calls]
  Pure deterministic assembly of the v2.0 JSON config from all extracted data.
  → emits config_ready
```

**Total LLM calls per run: 4** (tracking discovery, auth discovery, status extraction, mapping suggestion)

---

## Two Pause Points

The pipeline can pause and wait for human input at two points:

```
┌─────────────┐     clarification_needed SSE      ┌──────────────────────┐
│  Pipeline   │ ─────────────────────────────────► │  User picks endpoint  │
│  (paused)   │ ◄───────────────────────────────── │  PUT /clarification   │
└─────────────┘     clarification_event.set()      └──────────────────────┘

┌─────────────┐     mapping_review SSE             ┌──────────────────────┐
│  Pipeline   │ ─────────────────────────────────► │  User confirms table  │
│  (paused)   │ ◄───────────────────────────────── │  PUT /mappings        │
└─────────────┘     review_event.set()             └──────────────────────┘
```

Each pause is an `asyncio.Event`. The route handler sets the event; the pipeline's `await event.wait()` unblocks.

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/sessions` | Create session, get `session_id` |
| GET | `/api/v1/sessions/{id}/stream` | Open SSE stream, start pipeline |
| PUT | `/api/v1/sessions/{id}/clarification` | Resume after user picks endpoint |
| GET | `/api/v1/sessions/{id}/mappings` | Fetch suggested status mappings |
| PUT | `/api/v1/sessions/{id}/mappings` | Submit confirmed mappings, resume pipeline |
| POST | `/api/v1/sessions/{id}/test-endpoint` | Run live E2E test (independent of pipeline) |
| GET | `/api/v1/sessions/{id}/config` | Fetch generated config JSON |
| GET | `/api/v1/sessions/{id}/download` | Download config as `.json` file |

Sessions are in-memory — they do not survive a server restart.

---

## E2E Endpoint Test

Independent of the pipeline. The user enters real credentials + an AWB number after Step 2, and the tester:

1. **Authenticates** — static header injection (api_key_header) or POST login → extract token (login_flow)
2. **Calls tracking endpoint** — places AWB in path / query / body per config
3. **Extracts current status** — navigates response JSON using dotted paths (e.g. `data.shipments[0].status`)
4. **Returns structured result** — success flag, detected status, duration, raw response

Result is stored in context and embedded in the final config under `test_run`.

---

## Output Config (v2.0 Schema)

```jsonc
{
  "schema_version": "2.0",
  "provider": { "name", "documentation_url", "base_url" },

  "authentication": {
    "type": "api_key_header | login_flow | basic | oauth2 | none | unknown",
    "credentials_required": ["api_key"],
    "inject_header": "X-Api-Key",
    "inject_header_format": "{api_key}",
    "login_endpoint": { ... },   // only for login_flow / oauth2
    "error_cases": { ... }
  },

  "tracking": {
    "endpoint": { "method", "url", "awb_location", "awb_field_name", "request_body_template" },
    "response_mapping": {
      "current_status": "data.status",   // dotted path
      "scan_history": { "field", "item_fields": { ... } }
    },
    "raw_response_schema": { ... }
  },

  "error_handling": {
    "0_body_level_error": {              // checked even on HTTP 200
      "check_field": "success",
      "success_value": "true",
      "message_field": "message",
      "detection_logic": "...",
      "action": "..."
    },
    "1_auth_failure":             { "indicators": ["HTTP 401", "HTTP 403"], "action": "..." },
    "2_invalid_request":          { "indicators": ["HTTP 400"], "action": "..." },
    "3_awb_not_found":            { "indicators": ["HTTP 404", "empty body"], "action": "..." },
    "4_rate_limited":             { "indicators": ["HTTP 429"], "action": "..." },
    "5_server_error":             { "indicators": ["HTTP 5xx"], "action": "..." },
    "6_unexpected_response_shape":{ "indicators": ["status path resolves to null"], "action": "..." },
    "rate_limiting":              { "requests_per_minute": 60, "note": "..." }
  },

  "status_map": [                        // array, not object — order preserved
    { "provider_code": "DL", "label": "Delivered", "gokwik_status": "delivered", "is_terminal": true }
  ],

  "implementation_guide": {
    "steps": [
      { "step": 1, "title": "Authenticate", "description": "...", "ref": "authentication" },
      { "step": 2, "title": "Build tracking request", "description": "...", "ref": "tracking.endpoint" },
      { "step": 3, "title": "Check for errors", "description": "...", "ref": "error_handling" },
      { "step": 4, "title": "Extract current status", "description": "...", "ref": "tracking.response_mapping" },
      { "step": 5, "title": "Map to GoKwik status", "description": "...", "ref": "status_map" }
    ]
  },

  "test_run": {
    "credentials_used": { "api_key": "..." },
    "awb_tested": "12345ABCDE",
    "outcome": { "success": true, "current_status_detected": "IN_TRANSIT", "duration_ms": 843 },
    "raw_tracking_response": { ... }
  }
}
```

---

## LLM Abstraction

`LLMClient` wraps any provider behind a single `.complete(system, user, response_format)` interface.

- **Structured output:** The Pydantic model's JSON schema is appended to the system prompt. The LLM is instructed to return raw JSON only. The response is parsed with `json.loads()` and validated by Pydantic.
- **Retry logic:** On 429 / 503 / quota errors, retries up to 4 times with exponential backoff (1s → 2s → 4s).
- **Supported providers:** `gemini`, `anthropic`, `openai` (covers Groq, NVIDIA, etc. via OpenAI-compatible endpoint).

All provider config lives in `.env` — no code changes needed to switch.

---

## 5-Step UI Flow

```
Step 1 Input       → POST /sessions → open SSE stream
Step 2 APIs        ← step_complete:discover_apis (rendered from SSE data)
                   ← clarification_needed (if ambiguous) → PUT /clarification
Step 3 Credentials → dynamic fields built from auth_api.credentials_required
                   → POST /test-endpoint (optional live test)
Step 4 Mapping     ← mapping_review SSE (table pre-populated)
                   → PUT /mappings
Step 5 Config      ← step_complete:generate_config (full JSON rendered with Prism.js)
                   → copy / download
```

The SSE connection stays open from Step 1 until `config_ready` is received. The pipeline runs server-side; the UI just reacts to events.

---

## GoKwik Canonical Statuses (20 total)

`order_placed` → `pickup_pending` → `pickup_scheduled` → `out_for_pickup` → `picked_up` → `in_transit` → `reached_destination_hub` → `out_for_delivery` → `delivered`

Failure branches: `delivery_failed`, `delivery_failed_customer_unavailable`, `delivery_failed_address_issue`, `delivery_failed_refused`

RTO branch: `rto_initiated` → `rto_in_transit` → `rto_delivered`

Other: `cancelled`, `lost`, `damaged`, `on_hold`, `unknown`
