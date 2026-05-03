# [PRD] Agentic Shipping Connectors — v2.0

- **Status:** Draft for review
- **Product area:** RTO (RTO-POD)
- **Last updated:** May 3, 2026
- **Replaces:** v1.0 (Apr 13, 2026)

---

## 0. What changed since v1

- **Productised:** Dashboard-initiated request flow (was: internal CLI for one engineer).
- **Scope honestly tightened:** This agent stops at producing a verified JSON config. Code generation is a separate, downstream PRD (not built yet).
- **Inputs:** URL only in MVP. PDF + Webhook docs deferred to Phase 2.
- **Approval gates:** 1 (was: 4).
- **Dedup:** Provider name + URL combo (was: not specified).
- **Notifications:** RTO-prefix Slack channel for in-flight steps + JIRA ticket created **only after all validations pass** (was: JIRA from the start).
- **B2C-only filter:** Discovery must reject B2B-only docs.
- **Test-fail handling:** Diagnostic classification — `auth_failure` / `awb_not_found` / `wrong_domain` / `unknown`. Note: response-shape mismatch is **not** a stop reason — the agent's LLM auto-remaps fields (matches `error_handling.6_unexpected_response_shape` in the existing codebase).
- **Status mapping:** Mapped to the GoKwik shipment-status enum owned by RTO Product (21 canonical values, schema field `gokwik_status`). Schema is the existing `schema_version: "2.0"` config emitted by the agent today.

---

## 1. Executive Summary

- **Problem.** Each new shipping-provider integration costs 2–4 weeks of engineering time on rote work. Backlog grows; merchants wait 4–12 weeks. Reference tickets: [RMS-1047](https://gokwik.atlassian.net/browse/RMS-1047), [RMS-1073](https://gokwik.atlassian.net/browse/RMS-1073), [RE-13072](https://gokwik.atlassian.net/browse/RE-13072).
- **Solution (MVP).** An internal-only agent that takes a public API doc URL, discovers the B2C tracking endpoint + auth method, maps provider statuses to the GoKwik shipment-status enum, runs a live test with real credentials, and produces a verified JSON config (10 L1 keys, schema v2.0) for downstream code-gen.
- **MVP includes.** Internal-only dashboard surface · URL input · 4 surfaced checks · Provider+URL dedup · Staging-vs-prod URL handling · Live test with diagnostic classification · 1 approval gate · RTO Slack channel + JIRA ticket created on validation-pass · JSON config output.
- **MVP excludes (Phase 2+).** Code generation · Merchant self-serve · PDF docs · Webhook docs · Multi-language code-gen · B2B flows.

---

## 2. Personas (bounded — 5)

| # | Persona | What they do here |
|---|---|---|
| P1 | **Internal Requestor** (CSM / Solutions Eng / Integration PM) | Submits the request, provides creds + AWB, confirms staging→prod URL if flagged |
| P2 | **RTO Product Approver** | Reviews the validated discovery + test result; approves or rejects the JSON config |
| P3 | **RTO Engineering Lead** | Receives the approved JSON config; owns the downstream code-gen agent (separate PRD) |
| P4 | **RTO Ops** | Watches the Slack channel for stuck/failed requests; triages |
| P5 | **Shipping Provider** | External — owns the docs and the live API. Indirect stakeholder, not a system user |

P1 and P2 are gated by GoKwik admin auth (existing). P3/P4 are Slack channel members.

---

## 3. Scope split

### 3.1 Future Scope (sequenced, will solve later)

- PDF documentation ingestion (Phase 2)
- Webhook documentation ingestion (Phase 2/3 — different agent flow)
- Merchant self-serve submission behind feature flag (Phase 2)
- Code generation from JSON config (separate PRD, downstream)
- Multi-language code-gen — Go, Node, Java (downstream of code-gen PRD)
- Connector drift detection — re-run agent on schedule (Phase 3)

### 3.2 Out of Scope (forever)

- B2B shipping flows (manifest APIs, bulk allocation, freight)
- Authentication / identity (existing admin auth)
- Production deployment (existing release process)
- Provider relationship management (Partnerships)
- Provider API SLA / uptime (provider responsibility)

---

## 4. Human-in-the-loop flow (MVP)

The flow has **3 human touchpoints**. Everything else is automated.

| Step | Actor | Action | What happens |
|---|---|---|---|
| **1** | P1 | Submits doc URL + provider hint on the dashboard | Slack post in `#rto-connector-agent`: "Step: Submitted · Status: started · By: @requestor" |
| **2** | Agent | Pre-flight (doc reachable, dedup) | Slack: pass/fail with reasons |
| **3** | Agent | Discovery (B2C endpoint, auth, status mapping) | Slack: discovered endpoint + auth + mapping coverage |
| **4** | Agent | Flags staging URL if detected | Slack: "⚠️ Staging URL detected: `{url}`. Awaiting prod URL from @requestor" |
| **5** | **P1** | **Confirms staging→prod URL (if flagged)** | Inputs prod base URL; agent rewrites host (path/query preserved) |
| **6** | **P1** | **Provides test creds + ≥1 AWB** | Agent runs live test |
| **7** | Agent | Live test → diagnostic on fail | Slack: per-AWB result + classification if fail |
| **8** | Agent | All validations passed → **creates JIRA ticket on RE Board** | Slack: "✅ Validated. JIRA: RE-XXXX. Awaiting approval" |
| **9** | **P2** | **Approves or rejects JSON config** | Slack: "✅/🔴 Decision: {approve/reject} by @approver" · JIRA transitions |
| **10** | Agent | If approved: emits JSON config to handoff location | Slack: "📦 Config handed off: `{path}`" |

**Key decision:** JIRA tickets are NOT created on submission. They're created only when steps 1–7 all pass. Avoids polluting JIRA with abandoned/failed requests.

[**PM INPUT NEEDED**: Figma flow + dashboard mockups for steps 1, 5, 6, 9.]

---

## 5. User stories

Stories simplified — metrics + success criteria are placeholders, to be filled pre-engineering.

##### US-1 — Submit a connector request

**As an** Internal Requestor, **I want to** submit a public API doc URL with an optional provider-name hint, **so that** the agent begins discovery without me reading the full doc.

*Example.* Sandeep (CSM) pastes `https://apidocs-rapidshyp.netlify.app/docs/...`, types "RapidShyp", submits. Sees a live progress UI streaming step-by-step results from the agent.

*Metrics & success criteria: [TBD — placeholder]*

---

##### US-2 — See live pre-flight + discovery checks

**As an** Internal Requestor, **I want to** see results of every step (doc reachable, dedup, B2C endpoint, auth method, status mapping, staging-URL flag) live in the dashboard and Slack.

*Example A — happy path.* Doc reachable ✅ · Not duplicate ✅ · B2C endpoint found at confidence 0.92 ✅ · Auth: api_key_header ✅ · Status mapping: 27 codes mapped ✅ · Not a staging URL ✅.

*Example B — B2B-only.* "No B2C tracking endpoint found — this doc appears B2B-only. Submit a B2C-specific URL." Pipeline halts.

*Metrics & success criteria: [TBD — placeholder]*

---

##### US-3 — Block exact duplicates; warn on near-duplicates

**As an** Internal Requestor, **I want** the system to block re-submissions of the same provider+URL combo.

- Exact match (same provider + same URL): hard block; show prior config; P2 can override with reason.
- Same provider + new URL: soft note; allow proceed (treats as updated config).
- Name typo (camelCase, whitespace): treated as match (case-insensitive + whitespace-normalised).

*Metrics & success criteria: [TBD — placeholder]*

---

##### US-4 — Confirm prod URL if doc shows staging

**As an** Internal Requestor, **I want** the agent to flag if the discovered URL looks like staging/sandbox/UAT, **so that** my live test isn't doomed by the wrong domain.

- Heuristic: discovered URL host contains any of `staging`, `sandbox`, `uat`, `dev`, `qa`, `test.`, `staging-api.`.
- If matched: dashboard shows the discovered URL and asks for the prod base URL.
- Agent does host-only rewrite — preserves path, query, headers, body template.
- The JSON config stores both the original `tracking.endpoint.url` (rewritten to prod) and a flag `tracking.endpoint.host_rewritten: true` with `tracking.endpoint.discovered_host_original` for audit.
- Fallback (heuristic missed it): if live test fails with DNS error or persistent 404 across all AWBs, dashboard offers: "Was this a staging URL? Enter prod URL manually."

*Example.* Discovery returns `https://staging.api.delhivery.com/api/v1/track/{awb}`. Agent flags. Sandeep enters `https://api.delhivery.com`. Agent rewrites. Test runs against the prod URL.

*Metrics & success criteria: [TBD — placeholder]*

---

##### US-5 — Live test with diagnostic classification

**As an** Internal Requestor, **I want** the agent to call the real API and tell me **why** it failed, **so that** I know whether to fix creds, fix AWB, or fix the URL.

The agent's live test maps to the codebase's existing 7-scenario error-handling logic. From the requestor's perspective, failures collapse into four named buckets:

| Classification | Triggered by | What the requestor does |
|---|---|---|
| **auth_failure** | HTTP 401/403, or 200 + `success=false` with `unauthori`/`invalid token` in message | Regenerate creds from provider dashboard, retry |
| **awb_not_found** | HTTP 404, or 200 + empty data, or 200 + `success=false` with `not found`/`invalid awb` | Use a different AWB known to be in transit |
| **wrong_domain** | DNS failure or persistent 404 across all AWBs (covers staging-URL case) | Confirm/enter prod base URL manually (US-4 fallback) |
| **unknown** | Anything else (HTTP 5xx, malformed body, rate-limited, unexpected shape) | Surface raw HTTP status + body excerpt; agent retries on transient codes (429/5xx) |

**Important:** if the response shape doesn't match what discovery extracted (provider added a wrapper key, renamed a field), this is **NOT a stop reason**. The agent's LLM is invoked again to re-derive `tracking.response_mapping` paths from the raw response and the test continues. This matches the codebase's `error_handling.6_unexpected_response_shape` action: log, retry mapping, do not abort.

*Metrics & success criteria: [TBD — placeholder]*

---

##### US-6 — Single approval gate; JSON config handoff

**As the** RTO Product Approver, **I want** to review the validated discovery + test result on one screen and approve or reject.

- Approval screen shows: endpoint, auth, status_map, test_result, staging→prod rewrite (if any), implementation_guide.
- Approve → JSON written to handoff location · JIRA transitions to "Approved — Ready for Code-Gen" · Slack post.
- Reject → JIRA transitions to "Rejected — Resubmit" with comment · Slack post.

*Metrics & success criteria: [TBD — placeholder]*

---

## 6. Surfaced checks (4)

| # | Check | Pass criterion | Latency target (P95) |
|---|---|---|---|
| 1 | Doc reachable + parseable + dedup | URL 2xx; content ≥ 1 KB; not a duplicate provider+URL | ≤ 10s |
| 2 | B2C tracking endpoint + auth method discovered | ≥1 endpoint at confidence ≥ 0.7; auth named (one of `none` / `api_key_header` / `login_flow` / `oauth2` / `basic`) | ≤ 90s |
| 3 | Staging-vs-prod URL classified | URL flagged if matches staging indicators; user can confirm/override | ≤ 2s after discovery |
| 4 | Live test pass on ≥1 AWB | ≥1 AWB returns 2xx + parseable + maps to a value in the GoKwik shipment-status enum | ≤ 60s for ≤5 AWBs |

If 1–3 fail: pipeline halts; Slack notification fires.
If 4 fails with `auth_failure` / `awb_not_found` / `wrong_domain`: requestor amends and retries up to 3×.
If 4 fails with `unknown` and the underlying issue is response-shape mismatch: agent re-derives `response_mapping` paths and continues — no human action required.

---

## 7. Staging vs Prod URL handling (called out)

**Why this is a real problem.** Many provider docs (Delhivery, Shiprocket, BlueDart) document staging/sandbox URLs in their examples. The agent extracts whatever the doc shows. If the requestor provides prod credentials and tries to test against a staging URL, every call fails — and the diagnosis without this check is misleading.

**Detection (heuristic, not exhaustive):** discovered URL host contains any of `staging`, `sandbox`, `uat`, `dev`, `qa`, `test.`, or `staging-api.`.

**UX when flagged:**
- Dashboard panel: "We extracted `{staging_url}` from the doc. This looks like a staging environment. Please confirm the production base URL."
- Input field for prod base URL (e.g. `https://api.delhivery.com`).
- Agent does host-only rewrite — preserves path, query, headers, body template.
- JSON config stores `tracking.endpoint.host_rewritten: true` and `tracking.endpoint.discovered_host_original` so audit trail is clear.

**Fallback (heuristic missed it):** if live test fails with DNS error or persistent 404 across all AWBs, dashboard offers: "Was this a staging URL? Enter prod URL manually."

[**TECH DESIGN: Engineering owns** the rewrite implementation, indicator regex tuning, and DNS-failure detection.]

---

## 8. JSON output config — schema (v2.0, matches existing codebase)

The agent emits a single JSON file per approved request, schema version `"2.0"`, with **10 L1 keys**. This matches what `backend/generator/storage.py` writes today. Field-level details are in `models/status_mapping.py` and the existing config_generator. Section §17 has a sample.

| L1 key | Type | What it captures |
|---|---|---|
| `schema_version` | string | Version identifier — `"2.0"` today; bumped on breaking schema changes. |
| `generated_at` | ISO-8601 timestamp | When the agent emitted this config. |
| `provider` | object | Provider metadata: `name`, `documentation_url` (the source doc URL), `base_url`. |
| `authentication` | object | Auth block. `type` is one of: `none` / `api_key_header` / `login_flow` / `oauth2` / `basic` / `unknown`. Type-specific fields: `inject_header` + `inject_header_format` for header-based; `login_endpoint` for login_flow; `static_headers`; `credentials_required` (list); `error_cases` (per-symptom indicators + actions). |
| `tracking` | object | Three sub-blocks. `endpoint` — `method`, `url`, `base_url`, `path`, `content_type`, `awb_location` (one of `path`/`query`/`body`), `awb_field_name`, `required_headers`, `query_params`, `request_body_template`. `response_mapping` — dotted-path map for `current_status` (mandatory), `awb_number`, `timestamp`, `origin_city`, `destination_city`, `weight_grams`, `scan_history`. `raw_response_schema` — a JSON Schema fragment describing the provider's response shape. |
| `error_handling` | object | Numbered scenarios `0_body_level_error` through `6_unexpected_response_shape` plus `rate_limiting`. Each scenario carries `_doc`, `indicators`, and an `action` string. The numbered sequence is the order the consumer evaluates after every API call. |
| `status_map` | array | Ordered list — preserves provider's status sequence. Each item: `provider_code`, `label`, `gokwik_status` (one of the 21 canonical GoKwik shipment statuses owned by RTO Product), `is_terminal` (boolean). |
| `implementation_guide` | object | `_doc` + ordered `steps`. Each step: `step` (number), `title`, `description`, `ref` (which section of this config it points to). Code-gen agent reads this top-down. |
| `implementation_hints` | array | Free-form strings — provider-specific gotchas the agent surfaces (e.g. "always uppercase the AWB"). Often empty. |
| `test_run` | object | `_doc` + `credentials_used` (the test-only creds — flagged "do not commit"), `awb_tested`, `outcome` (`success`, `stage_reached`, `current_status_detected`, `duration_ms`, `error`, `debug_note`), and `raw_tracking_response` (full provider response from the test). |

**GoKwik shipment-status enum (21 values, owned by RTO Product):** `order_placed` · `pickup_pending` · `pickup_scheduled` · `out_for_pickup` · `picked_up` · `in_transit` · `reached_destination_hub` · `out_for_delivery` · `delivered` · `delivery_failed` · `delivery_failed_customer_unavailable` · `delivery_failed_address_issue` · `delivery_failed_refused` · `rto_initiated` · `rto_in_transit` · `rto_delivered` · `cancelled` · `lost` · `damaged` · `on_hold` · `unknown`.

**Auth-type enum (6 values):** `none` · `api_key_header` · `login_flow` · `oauth2` · `basic` · `unknown`.

---

## 9. Notifications

### 9.1 Slack — `#rto-connector-agent` (channel name TBD, must have RTO prefix)

A message fires for every step with this payload shape:

```
Step: {step_name}
Status: {started | passed | failed | needs_input}
By: @{actor}                ← requestor / agent / approver
Provider: {provider_name}
Details: {one-line context — discovered URL, fail classification, etc.}
JIRA: {ticket_id or "not yet created"}
```

| Step | Status values | Actor |
|---|---|---|
| Submitted | started | P1 |
| Pre-flight | passed / failed | agent |
| Discovery | passed / failed | agent |
| Staging URL flagged | needs_input | agent |
| Prod URL confirmed | passed | P1 |
| Creds + AWB provided | passed | P1 |
| Live test | passed / failed_attempt_N / needs_triage | agent |
| JIRA ticket created | passed | agent (after validations pass) |
| Approval | approved / rejected | P2 |
| Config handoff | passed | agent |

### 9.2 JIRA — RE Board

JIRA ticket is created **only after step 7 (live test) passes**. Before that, no ticket.

**Ticket description template:**

```
Provider: {provider_name}
Doc URL (source): {doc_url}
Base URL: {provider.base_url}
Tracking URL (used for test): {tracking.endpoint.url}
Host rewritten from staging? {yes/no — original: {discovered_host_original}}
Requestor: {requestor email/handle}
Submitted at: {ISO timestamp}

Auth type: {authentication.type}
Status map coverage: {N codes mapped}
Live test: {pass_count} / {total} AWBs passed · stage_reached = {complete | tracking | auth}

JSON config: {path or "pending approval"}
Approval: {pending | approved by {approver} at {ts} | rejected — {reason}}

Slack thread: {link to first message in #rto-connector-agent}
```

- **Type:** Task
- **Labels:** `connector-agent`, `shipping`, `rto`
- **Custom fields:** `provider_name`, `doc_url`, `request_id`, `agent_version`
- **Status flow:** `Awaiting Approval` → `Approved — Ready for Code-Gen` OR `Rejected — Resubmit`

---

## 10. SOP & Troubleshooting

### 10.1 CSM / Internal Requestor (P1)

**SOP — submitting a request:**
1. Confirm with the merchant that the shipping provider's doc URL is publicly accessible (no login wall).
2. Have ready: (a) public doc URL, (b) test API credentials valid for prod, (c) ≥1 in-transit AWB.
3. Submit on dashboard. Watch Slack `#rto-connector-agent` thread for the request.
4. If staging URL flagged → confirm prod base URL with provider, paste in.
5. Provide creds + AWB when prompted.
6. Wait for approval.

**Troubleshooting:**

| Symptom | Likely cause | What to do |
|---|---|---|
| "Doc unreachable" | URL behind login or 4xx | Find public doc URL; ping provider |
| "B2B-only doc" | Doc describes manifest/bulk APIs only | Ask provider for B2C tracking-by-AWB doc URL |
| "Confidence < 0.7" | Doc is unstructured, multi-page | Submit a deep-link directly to the tracking section |
| `auth_failure` | Token wrong / expired / wrong header name | Regenerate from provider dashboard; verify the header name in the discovered config |
| `awb_not_found` | AWB not yet scanned, or wrong format | Use a different AWB known to be in transit; check format (some providers strip leading zeros) |
| `wrong_domain` | Doc had staging URL only | Get prod base URL from provider; paste in |
| `unknown` (response shape mismatch) | Provider response shape changed since doc was written | **No action needed** — agent's LLM auto-remaps and retries. If still failing after retry, ping P3 |

### 10.2 RTO Product Approver (P2)

**SOP — reviewing a config:**
1. Open the Slack notification or JIRA ticket from RE Board.
2. Review on the approval screen: endpoint URL (verify it's prod, not staging), auth `type`, `status_map` coverage and terminal flags, `test_run.outcome`.
3. Spot-check 2–3 status mappings against provider doc — agent occasionally guesses wrong on `is_terminal`.
4. Approve OR reject with a written reason.
5. Hand off Slack thread to RTO Eng Lead (P3) for downstream pickup.

**Reject if:**
- `status_map` coverage looks materially low for the provider's lifecycle (no `delivered`, no `rto_*`, etc.)
- Discovered endpoint is clearly B2B (manifest/bulk parameters)
- `tracking.endpoint.url` still points to staging despite the rewrite check
- `authentication.type = unknown` (manual inspection required)
- `test_run.outcome.success = false` and the diagnosis is not yet resolved

### 10.3 RTO Engineering Lead (P3)

**SOP — consuming the config:**
1. Watch `#rto-connector-agent` for "Config handed off" message.
2. Pick up the JSON file from the handoff location.
3. Pass to the (separate) code-gen agent OR hand-craft a connector if code-gen agent not yet built.
4. If config has issues, comment in JIRA and ping P2 to reject + resubmit.

**Troubleshooting:**

| Symptom | What to do |
|---|---|
| Config missing fields code-gen needs | Comment on JIRA; request schema update; bump `schema_version` |
| Provider broke the API after handoff | Re-run agent fresh against current docs (creates a new request) |
| Agent crashed mid-flow | Slack alerts P3+P4; check agent logs; auto-retry already attempted |

### 10.4 RTO Ops (P4)

**SOP — channel watch:**
1. Watch `#rto-connector-agent`. Specifically: `failed_attempt_3` and `needs_triage` events.
2. If a request is stuck in `needs_input` for >24h, ping the requestor.
3. If multiple agent crashes in a day, escalate to P3 + on-call.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| LLM hallucinates non-existent endpoint | Live test gate catches before approval |
| LLM picks B2B endpoint when B2C exists | Explicit B2C-detection rules; P2 review |
| Staging URL slips through to prod handoff | §7 staging detection; P2 spot-check during approval |
| Multi-page docs (only first page fetched) | MVP: requestor submits deep-link; Phase 2: doc-crawl |
| Credentials leaked in logs | Encrypted in transit + at rest; redaction; never written to JSON config outside `test_run.credentials_used`. [TECH DESIGN: cipher + key rotation] |
| `test_run.credentials_used` block is downstream-leaked | Mark file as restricted; gate handoff location to RTO Eng group only; consider scrubbing this block before code-gen handoff |
| P2 bottleneck (single approver) | SLA tracked; if breached 3×/month, add second approver |
| Provider API outage during test | Detect 5xx + retry once; classify persistent failures as `unknown` |
| JIRA API down | Slack remains primary channel; ticket creation queued + retried |

---

## 12. Phased rollout

- **MVP (Q3 2026, target end of July):** Internal-only · URL · API · B2C · 4 surfaced checks · Provider+URL dedup · Staging→prod handling · Live test + diagnostic · 1 approval gate · RTO Slack + JIRA-on-validation · JSON config output. **Launch criteria:** 2 successful end-to-end runs (e.g. RapidShyp + Shiprocket) before opening to all internal requestors.
- **Phase 2 (Q4 2026):** PDF docs · Status-mapping coverage threshold visible · Merchant self-serve behind flag · Multi-approver if bottleneck materialises.
- **Phase 3 (Q1 2027+):** Webhook docs · Drift detection · Code-gen agent integration · B2B (only if business case justifies).

---

## 13. Dependencies

- LLM provider (Gemini 2.5 Flash) — API quota
- JIRA Cloud (RE board) — project access + custom fields
- Slack workspace — `#rto-connector-agent` channel + bot user
- GoKwik shipment-status enum — owned by RTO Product (21 canonical values, schema field `gokwik_status`)
- Internal admin dashboard — hosting surface
- Code-gen agent (downstream PRD) — eventual consumer of the JSON config

---

## 14. Design

**Status: ❌ MISSING — blocks GO.** Five surfaces described, none designed:

1. New Connector Request form (URL + provider hint + submit + live progress).
2. Pre-flight + discovery results panel (4 checks + endpoint + auth + status_map preview).
3. Staging→prod URL confirm panel.
4. Live test panel (creds + AWBs + per-AWB result + diagnosis).
5. Approval review screen (P2's single-page summary).

[**PM INPUT NEEDED**: Figma links OR explicit "Design — N/A" rationale (implausible — 5 surfaces).]

---

## 15. Companion brief (1-page shareable)

> **Agentic Shipping Connectors — Build Brief**
>
> **Problem.** Each new shipping-provider integration costs 2–4 weeks of rote engineering work. Backlog grows; merchants wait 4–12 weeks.
>
> **Solution (MVP).** An internal dashboard agent that takes a public API doc URL, discovers the B2C tracking endpoint + auth, maps statuses to the GoKwik shipment-status enum, runs a live test with real credentials, and produces a verified JSON config (schema v2.0, 10 L1 keys, matches the agent's existing output) for downstream code-gen. One human approval before handoff.
>
> **Differentiators from v1.** RTO-prefix Slack channel for in-flight visibility · JIRA ticket created only after validations pass · Staging-vs-prod URL handling baked in · Diagnostic test failure classification (`auth_failure` / `awb_not_found` / `wrong_domain` / `unknown`) · Response-shape mismatch is auto-recovered by the LLM, not a stop.
>
> **Each team's role.** Product owns flow + schema documentation + SOP. RTO Eng owns the agent + integrations. Design owns 5 screens. Downstream code-gen agent owners (separate PRD) consume the JSON config.
>
> **NOT in MVP.** Code generation · Merchant self-serve · PDF docs · Webhook docs · B2B flows.
>
> **Composition.** Producer (this agent) → JSON config → Consumer (code-gen agent, separate PRD). Approval gate sits between producer and consumer.

---

## 16. Open questions

1. Designs for 5 surfaces.
2. Slack channel name confirmation (must have RTO prefix; suggest `#rto-connector-agent`).
3. JSON schema sign-off by code-gen agent owners (when identified) — schema v2.0 baseline already exists in code.
4. Baseline metrics (current manual time-to-connector, backlog size).
5. JIRA custom-field creation: `provider_name`, `doc_url`, `request_id`, `agent_version`.
6. Test-creds storage policy — confirm with security pre-MVP. Specifically whether `test_run.credentials_used` should be scrubbed before code-gen handoff.
7. Override RBAC for dedup blocks — P2-only or also P3?

---

## 17. Appendix A — Sample JSON config (abbreviated, schema v2.0)

Truncated for readability. The full RapidShyp sample (in conversation) shows the exact shape.

```json
{
  "schema_version": "2.0",
  "generated_at": "2026-05-03T15:28:33Z",
  "provider": {
    "name": "RapidShyp",
    "documentation_url": "https://apidocs-rapidshyp.netlify.app/docs/...",
    "base_url": "https://api.rapidshyp.com"
  },
  "authentication": {
    "type": "api_key_header",
    "credentials_required": ["api_key"],
    "inject_header": "rapidshyp-token",
    "inject_header_format": "{api_key}",
    "static_headers": {"Content-Type": "application/json"},
    "login_endpoint": null,
    "error_cases": {
      "invalid_credentials": {"indicators": ["HTTP 401", "HTTP 403"], "action": "Surface error to operator. Do not auto-retry."}
    }
  },
  "tracking": {
    "endpoint": {
      "method": "POST",
      "url": "https://api.rapidshyp.com/rapidshyp/apis/v1/track_order",
      "base_url": "https://api.rapidshyp.com",
      "path": "/rapidshyp/apis/v1/track_order",
      "content_type": "application/json",
      "awb_location": "body",
      "awb_field_name": "awb",
      "required_headers": {"Content-Type": "application/json", "rapidshyp-token": "<API-KEY>"},
      "query_params": {},
      "request_body_template": {"awb": "", "orderId": "", "contact": "", "email": ""},
      "host_rewritten": false,
      "discovered_host_original": null
    },
    "response_mapping": {
      "current_status": "records[0].shipment_details[0].current_tracking_status_desc",
      "awb_number": "records[0].shipment_details[0].awb",
      "timestamp": "records[0].shipment_details[0].current_status_date",
      "scan_history": {
        "field": "records[0].shipment_details[0].track_scans",
        "item_fields": {"status": "", "timestamp": "", "location": "", "remarks": ""}
      }
    },
    "raw_response_schema": { "type": "object", "properties": { "...": "..." } }
  },
  "error_handling": {
    "0_body_level_error": {"check_field": "success", "success_value": "true", "message_field": "msg", "action": "Classify error from message field..."},
    "1_auth_failure":      {"indicators": ["HTTP 401", "HTTP 403"], "action": "Surface error to operator..."},
    "2_invalid_request":   {"indicators": ["HTTP 400"], "action": "..."},
    "3_awb_not_found":     {"indicators": ["HTTP 404", "HTTP 200 with empty data"], "action": "..."},
    "4_rate_limited":      {"indicators": ["HTTP 429"], "action": "Exponential backoff..."},
    "5_server_error":      {"indicators": ["HTTP 500", "HTTP 502", "HTTP 503"], "action": "..."},
    "6_unexpected_response_shape": {"indicators": ["mapping path resolves to null"], "action": "Re-derive response_mapping via LLM, do not abort."},
    "rate_limiting": {"requests_per_minute": null, "recommended_default": "Max 60 req/min"}
  },
  "status_map": [
    {"provider_code": "SCB", "label": "Shipment Booked",   "gokwik_status": "order_placed",      "is_terminal": false},
    {"provider_code": "PUC", "label": "Pickup Completed",  "gokwik_status": "picked_up",         "is_terminal": false},
    {"provider_code": "INT", "label": "In Transit",        "gokwik_status": "in_transit",        "is_terminal": false},
    {"provider_code": "OFD", "label": "Out for Delivery",  "gokwik_status": "out_for_delivery",  "is_terminal": false},
    {"provider_code": "DEL", "label": "Delivered",         "gokwik_status": "delivered",         "is_terminal": true},
    {"provider_code": "RTO_DEL","label": "RTO Delivered",  "gokwik_status": "rto_delivered",     "is_terminal": true}
    /* ... full list = 27 entries for RapidShyp ... */
  ],
  "implementation_guide": {
    "steps": [
      {"step": 1, "title": "Inject API key into request headers", "ref": "authentication"},
      {"step": 2, "title": "Build and send tracking request",     "ref": "tracking.endpoint"},
      {"step": 3, "title": "Check for errors",                    "ref": "error_handling"},
      {"step": 4, "title": "Extract current status",              "ref": "tracking.response_mapping.current_status"},
      {"step": 5, "title": "Map to GoKwik status",                "ref": "status_map"}
    ]
  },
  "implementation_hints": [],
  "test_run": {
    "_doc": "⚠️ TEST CREDENTIALS — never commit or deploy these values.",
    "credentials_used": {"api_key": "<redacted>"},
    "awb_tested": "27990211563133",
    "outcome": {
      "success": true,
      "stage_reached": "complete",
      "current_status_detected": "Delivered",
      "duration_ms": 427,
      "error": null
    },
    "raw_tracking_response": { "...": "full provider response stored verbatim ..." }
  }
}
```

---

**PRD Version:** 2.0 · **Last Updated:** May 3, 2026 · **Status:** Draft for review — Design pending (blocks GO)
