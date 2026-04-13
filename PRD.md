# Product Requirements Document: Shipping Connector Agent

## 1. Executive Summary

### Problem Statement
GoKwik receives regular requests to integrate new shipping providers, but these integrations are frequently deprioritized due to lack of engineering bandwidth. Each connector integration typically requires 2-4 weeks of manual API analysis, status mapping, and code generation, creating a bottleneck in time-to-market for new provider support.

### Proposed Solution
An LLM-powered **Shipping Connector Agent** that automatically generates production-ready Python shipping provider connectors from API documentation in under 1 hour. The system extracts tracking and authentication APIs, maps provider-specific statuses to GoKwik canonical statuses, and generates testable code—reducing manual engineering effort by 80% while maintaining quality through human review gates.

### Success Criteria
- **Connector generation time**: < 1 hour (end-to-end from documentation URL to deployable code)
- **Time reduction**: 80% reduction in connector development effort vs. manual implementation
- **Code quality**: 100% syntax validation + function signature verification before user testing
- **Testing confidence**: Live sandbox execution with real credentials enables pre-deployment validation
- **Adoption**: Generated connectors used for ≥ 3 new providers within Q2 2026
- **Traceability**: 100% of requests tracked in Jira with audit trail of approvals and testing

---

## 2. User Experience & Functionality

### User Personas

1. **Product Manager (Approver)**
   - Reviews discovered APIs and status mappings
   - Approves or rejects connector generation
   - Needs visibility into request history via Jira

2. **Engineering Manager (Approver)**
   - Reviews technical details of generated code
   - Approves final connector before deployment
   - Traces decision history in Jira

3. **Integration Engineer (Operator)**
   - Submits API documentation URLs
   - Tests generated connectors with provider credentials
   - Downloads and prepares connector for deployment

4. **Operations/DevOps (Deployer)**
   - Receives approved connector package
   - Deploys to production manually
   - Updates Jira ticket with deployment confirmation

### User Stories

#### Story 1: Connector Request Submission
**As an** Integration Engineer,  
**I want to** submit a shipping provider's API documentation URL,  
**So that** the system automatically discovers and generates a connector.

**Acceptance Criteria:**
- [ ] System accepts URL to public API docs (Postman collection, GitHub markdown, OpenAPI spec, public PDF)
- [ ] System creates a Jira ticket on RE board immediately with status "In Progress"
- [ ] SSE stream provides real-time progress: "Fetching docs" → "Discovering APIs" → "Extracting statuses" → "Generating code"
- [ ] Jira ticket link displayed in UI
- [ ] User can optionally provide provider name hint to improve LLM accuracy
- [ ] Session saved for ≤ 24 hours in case of accidental refresh

#### Story 2: API Discovery Review & Approval
**As a** Product Manager,  
**I want to** review discovered tracking and auth APIs,  
**So that** I can confirm accuracy before code generation proceeds.

**Acceptance Criteria:**
- [ ] UI displays discovered endpoints with: URL, HTTP method, headers, query params, request/response schema
- [ ] Confidence score shown for each discovery (LLM's uncertainty estimate)
- [ ] PM can view provider documentation excerpt used for discovery
- [ ] PM can approve or reject discovery
- [ ] Approval updates Jira ticket: "APIs Approved by [User]"
- [ ] Rejection creates Jira comment with reason; process halts

#### Story 3: Status Mapping Review & Confirmation
**As a** Product Manager,  
**I want to** review and adjust mappings from provider-specific statuses to GoKwik statuses,  
**So that** tracking data is correctly normalized.

**Acceptance Criteria:**
- [ ] Table displays: Provider Status Code | Description | Is Terminal? | LLM-suggested GoKwik Status | User-confirmed Status
- [ ] Each row has dropdown to select different GoKwik status
- [ ] Can see GoKwik status definitions (Pending, Picked, In Transit, Out for Delivery, Delivered, Failed, Returned)
- [ ] LLM's reasoning visible in tooltip
- [ ] Bulk actions: "Accept all suggestions" or "Reset to defaults"
- [ ] PM confirms mappings → Jira comment: "Status Mappings Approved by [User]"
- [ ] Confirmation triggers code generation

#### Story 4: Generated Code Review & Testing
**As an** Engineering Manager,  
**I want to** review the generated Python code,  
**So that** I can verify it meets our standards before testing.

**Acceptance Criteria:**
- [ ] Code shown in syntax-highlighted tabs: `connector.py`, `__init__.py`, `config.json`
- [ ] Code syntax validated (AST parse, no runtime errors)
- [ ] Required functions present: `authenticate()`, `track_shipment()`, `parse_tracking_response()`
- [ ] STATUS_MAP dict visible and non-empty
- [ ] EM can approve code or request regeneration
- [ ] Approval updates Jira: "Code Approved by [EM Name]"
- [ ] Code remains read-only for approval (no inline editing)

#### Story 5: Live Connector Testing
**As an** Integration Engineer,  
**I want to** test the generated connector with real provider credentials and AWB numbers,  
**So that** I can verify it works before deployment.

**Acceptance Criteria:**
- [ ] Dynamic credential input fields based on auth type (Bearer Token, API Key, Basic Auth, OAuth2, JSON)
- [ ] Credentials stored optionally with merchant association (checkbox: "Save for future testing")
- [ ] Stored credentials appear in dropdown for next session (can be deleted)
- [ ] AWB textarea accepts comma-separated list
- [ ] "Run Test" executes connector in sandbox: calls authenticate() → track_shipment() for each AWB
- [ ] Results show: AWB | Status ✓/✗ | Parsed Status | Raw Response | Error (if any)
- [ ] Test logs stored in Jira as comment
- [ ] Can run multiple tests without regenerating code
- [ ] Failed test does NOT block download but shows warning

#### Story 6: Connector Package Download & Deployment
**As a** DevOps Engineer,  
**I want to** download the approved and tested connector,  
**So that** I can deploy it to production.

**Acceptance Criteria:**
- [ ] "Download ZIP" button available after code approval
- [ ] ZIP contains: `connector.py`, `__init__.py`, `config.json`, `README.md` (usage instructions)
- [ ] ZIP naming: `{provider_name}_connector_{timestamp}.zip`
- [ ] README includes: auth setup, expected input/output, status mapping reference
- [ ] Download triggers Jira comment: "Connector Downloaded"
- [ ] After deployment, DevOps manually updates Jira: "Deployed to [environment] by [user]"

#### Story 7: Jira Ticket Lifecycle
**As a** PM/EM/Operator,  
**I want to** track connector request progress in Jira,  
**So that** stakeholders know status without checking the UI constantly.

**Acceptance Criteria:**
- [ ] Ticket created on **RE Board** immediately when request submitted
- [ ] Ticket type: "Task" (or "Connector Integration")
- [ ] Fields populated: Provider Name, Documentation URL, Requestor, Created Date
- [ ] Ticket transitions reflect UI state:
  - "In Progress" → Discovering APIs
  - "In Review" → Awaiting API Approval
  - "In Progress" → Code Generation
  - "In Review" → Awaiting Code Approval
  - "Ready for Testing" → Live test available
  - "Testing" → Test in progress
  - "Ready for Deployment" → Code approved, ready to download
  - "Deployed" → Manual update after DevOps deployment
- [ ] Comments auto-added for: API approval, status mapping approval, code approval, test results
- [ ] Link to live connector UI (ephemeral session link valid 24h)
- [ ] Assignee changes based on approval stage (PM → EM → DevOps)

### Non-Goals (MVP)

- **Code editing UI**: Generated code is read-only. Edits require manual post-download.
- **Multiple output languages**: Only Python codegen in MVP. Go/Java/Node support in v2.
- **Batch multi-provider generation**: Single provider per request in MVP.
- **Private/authenticated API doc fetching**: Only public URLs. Private docs must be manually copied/pasted or hosted publicly.
- **Automated deployment**: Manual deployment post-approval (no CI/CD integration in MVP).
- **Webhook/callback handling**: Only REST APIs in MVP.
- **Live provider credential validation**: System doesn't pre-validate credentials (only discovers auth type).
- **Connector versioning/updates**: Once deployed, old connectors remain. New URLs generate new connectors.

---

## 3. AI System Requirements

### Tool Requirements

**LLM Model**: Google Gemini 2.5 Flash (via LangChain)
- **Rationale**: Fast inference (~1-2s per call), cost-effective, handles long documentation (up to 100k tokens)
- **API Cost**: ~$0.075 / 1M input tokens. Typical connector: 3-5 calls × 5k tokens = ~$0.0004 per connector
- **Fallback**: Supports OpenAI-compatible providers (set via `LLM_PROVIDER` config)

**External Tools/APIs**:
- **Fetcher**: httpx for URL fetching (supports Postman collections, OpenAPI specs, raw markdown)
- **Jira API**: Create/update tickets on RE board
- **Storage**: Local filesystem `generated_connectors/{provider_name}/`

### Evaluation Strategy

**Quality Metrics** (per generated connector):

1. **API Discovery Accuracy**
   - Metric: Confidence score from LLM (0-1)
   - Target: ≥ 0.7 confidence for tracking API
   - Validation: Manual review by PM, then test with real credentials

2. **Status Mapping Correctness**
   - Metric: % of status codes correctly mapped to GoKwik enum
   - Target: ≥ 90% (user can fix remaining 10%)
   - Validation: During live testing, confirm mapped statuses match expected values

3. **Code Generation Quality**
   - Metric: Pass AST validation + function signature check
   - Target: 100% of generated code passes syntax check
   - Validation: Automated on generation, before user sees code

4. **Live Test Success Rate**
   - Metric: % of AWBs successfully tracked without auth/network errors
   - Target: ≥ 80% (assumes valid credentials)
   - Validation: User runs tests; logs stored in Jira

5. **Documentation Coverage**
   - Metric: % of provider's documented endpoints covered
   - Target: ≥ 1 tracking API + 1 auth method discovered per provider
   - Validation: Spot-check against provider's actual API docs

### Handling LLM Failures

- **Failed API Discovery**: Show error in UI → user can retry with different provider name hint
- **Hallucinated Endpoints**: PM reviews before code gen; can reject and restart
- **Status Mapping Errors**: User can adjust in UI; no hard failure
- **Code Generation Syntax Errors**: Caught by validator; regenerate with explicit error feedback to LLM

---

## 4. Technical Specifications

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend (Browser)                         │
│  5-Step Wizard: Input → APIs → Mapping → Code → Test           │
└──────────────────────┬──────────────────────────────────────────┘
                       │ (WebSocket/SSE)
                       ↓
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                               │
│                                                                   │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ Session Manager │  │ Agent Orchestrator│  │ Jira Integrator│  │
│  │ (pause/resume)  │  │ (pipeline steps) │  │ (ticket mgmt)  │  │
│  └─────────────────┘  └──────────────────┘  └────────────────┘  │
│         ↓                      ↓                      ↓           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            Pipeline Steps                                │   │
│  │  1. Fetch docs      → Fetcher                            │   │
│  │  2. Discover APIs   → APIDiscoveryAnalyzer (LLM)         │   │
│  │  3. Extract statuses → StatusExtractor (LLM)             │   │
│  │  4. Map statuses    → User confirmation (pause)          │   │
│  │  5. Generate code   → CodeGenerator (LLM + Jinja2)       │   │
│  │  6. Validate code   → CodeValidator (AST)                │   │
│  │  7. Store connector → save to disk                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│         ↓                                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            Supporting Services                           │   │
│  │  - LLMClient (Gemini API)                                │   │
│  │  - ConnectorTester (sandbox exec with exec())            │   │
│  │  - JiraClient (create/update tickets)                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
         ↓                          ↓                  ↓
    File System            Jira API             Google Gemini
 generated_connectors/      (RE Board)            (LLM calls)
```

### Data Flow

1. **Request Creation**
   - User submits URL → Backend creates session + Jira ticket
   - Jira ticket ID stored in session context
   - Jira transitions to "In Progress"

2. **Fetch → Discover → Extract**
   - Fetcher retrieves docs
   - APIDiscoveryAnalyzer calls Gemini to find tracking/auth APIs
   - StatusExtractor calls Gemini to identify provider status codes
   - All LLM calls logged with timestamps

3. **Pause for Approval**
   - APIs displayed in UI for PM review
   - If approved: trigger status mapping step
   - If rejected: update Jira "Rejected" + halt pipeline

4. **Status Mapping & Code Gen**
   - User confirms/adjusts status mappings
   - CodeGenerator calls Gemini with confirmed mappings + docs
   - Generated code validated via AST parser
   - Jira transitions to "Ready for Testing"

5. **Live Testing**
   - User submits credentials + AWBs
   - ConnectorTester executes generated code in sandbox (restricted namespace)
   - Results stored + Jira comment added with test summary
   - No blocking of download on test failure (warning only)

6. **Download & Manual Deployment**
   - User downloads ZIP → Jira comment "Downloaded"
   - DevOps deploys manually → Jira updated to "Deployed"

### Integration Points

**Jira Integration** (New)
- **API**: Jira Cloud REST API v2
- **Endpoint**: `https://{instance}.atlassian.net/rest/api/2/issue`
- **Auth**: API token (stored in `.env` as `JIRA_API_TOKEN`)
- **Board**: RE Board (ID to be configured in `.env` as `JIRA_RE_BOARD_ID`)
- **Ticket Fields**:
  - Summary: `Shipping Connector: {Provider Name}`
  - Description: Provider name, docs URL, requestor, creation timestamp
  - Type: Task
  - Labels: `connector-agent`, `shipping`
  - Assignee: Auto-set based on approval stage
  - Custom Fields: `connector_session_id`, `provider_name`, `docs_url`

**Jira Transitions**:
- Created → In Progress
- In Progress → In Review (awaiting API approval)
- In Review → In Progress (API approved)
- In Progress → Ready for Testing
- Ready for Testing → Testing (test run started)
- Testing → Ready for Deployment (approval pending)
- Ready for Deployment → Deployed (manual update)

**LLM API** (Existing)
- Provider: Google Gemini 2.5 Flash
- Auth: API key in `.env` as `LLM_API_KEY`
- Rate limit: 100 requests/min (sufficient for MVP)
- Fallback: If rate limited, user retries with backoff

**File Storage** (Existing)
- Path: `./generated_connectors/{provider_name}/`
- Files: `connector.py`, `__init__.py`, `config.json`
- Lifetime: Permanent (no auto-cleanup)
- Access: Read-only for integration engineers, writable by agent only

**Credential Storage** (New, Optional)
- **Storage Location**: Database table `TestCredentials` (schema TBD)
- **Fields**: `id`, `merchant_id`, `provider_name`, `auth_type`, `encrypted_credentials`, `created_at`, `session_id`
- **Encryption**: Use `.env` secret key for AES-256 encryption
- **Retention**: 30 days; auto-delete after expiry
- **Access Control**: User can view/delete own credentials only
- **Note**: Optional feature; users can test without saving

### Security & Privacy

**Credential Handling**
- [ ] Credentials NEVER logged in console/files
- [ ] Credentials transmitted over HTTPS only (TLS 1.2+)
- [ ] If stored: Encrypted at rest (AES-256-GCM)
- [ ] Session-scoped credentials: Cleared after test or 1 hour timeout
- [ ] Stored credentials: User must explicitly confirm before use

**Code Execution Safety**
- [ ] Generated code executed in restricted namespace (no `os`, `subprocess`, `sys` imports allowed)
- [ ] Timeout: 30s max per test (prevent infinite loops)
- [ ] Sandboxed with exec() + restricted globals dictionary
- [ ] Network calls only to provider's documented API endpoint

**API Documentation Safety**
- [ ] Only public URLs accepted in MVP
- [ ] URL validation: must start with http:// or https://
- [ ] No file:// or local paths accepted
- [ ] Fetched content scanned for suspicious patterns (TBD in security review)

**Jira Integration Security**
- [ ] Jira API token stored in `.env`, never committed to git
- [ ] Ticket links ephemeral (session-scoped, valid 24h)
- [ ] ACL checks: Only users in Jira project can approve
- [ ] Audit trail: All approvals logged with username + timestamp

**Data Retention**
- [ ] Session data: Deleted after 24 hours
- [ ] Test result logs: Kept in Jira comments indefinitely
- [ ] Generated code: Kept indefinitely (immutable)
- [ ] Test credentials: Deleted per retention policy (30 days default)

---

## 5. Approval & Deployment Workflow

### Approval Gates (Critical)

**Gate 1: API Discovery**
- Approver: Product Manager
- Approval Duration: ≤ 8 hours
- Decision: Approve APIs OR Reject and restart with hint
- Jira Update: Comment with approval/rejection + reason

**Gate 2: Status Mapping**
- Approver: Product Manager
- Approval Duration: ≤ 4 hours (user confirms mappings in UI)
- Decision: Confirm mappings OR adjust and reconfirm
- Jira Update: Transitions to "Code Generated"

**Gate 3: Code Review**
- Approver: Engineering Manager
- Approval Duration: ≤ 8 hours
- Decision: Approve code OR request regeneration
- Jira Update: Comment with approval + code review notes

**Gate 4: Testing**
- Approver: Integration Engineer
- Approval Duration: ≤ 4 hours
- Decision: Test passes → Ready for deployment; Test fails → Optional retry/debug
- Jira Update: Test results in comment; can retry without approval

**Gate 5: Deployment** (Manual)
- Deployer: DevOps/SRE
- Deployment Duration: ≤ 24 hours from approval
- Decision: Deploy to staging → prod
- Jira Update: Transitions to "Deployed"; includes deployment details

### Role-Based Access Control (ACL)

| Role | Can Generate | Can Approve APIs | Can Approve Code | Can Test | Can Deploy |
|------|---|---|---|---|---|
| Integration Engineer | ✓ | — | — | ✓ | — |
| Product Manager | — | ✓ | — | — | — |
| Engineering Manager | — | — | ✓ | — | — |
| DevOps/SRE | — | — | — | — | ✓ |
| Tech Lead | ✓ | ✓ | ✓ | ✓ | — |

**ACL Definition** (to be configured in `.env` or external auth service):
```
APPROVAL_ROLE_ACL={
  "api_approval": ["product_manager", "tech_lead"],
  "code_approval": ["engineering_manager", "tech_lead"],
  "jira_project_id": "RE",
  "jira_board_id": "..."
}
```

---

## 6. Risks & Mitigation

### Technical Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| LLM hallucination of endpoints | Generated code calls wrong API | Medium | PM review gate before code gen |
| Status mapping misalignment | Tracking data corrupted | Medium | User can adjust mappings; live testing catches it |
| Rate limiting on LLM API | Pipeline stalls | Low | 100 req/min quota sufficient; backoff retry |
| Long documentation (>100k tokens) | Timeout or cost explosion | Low | Truncate docs to 12k chars; log warning |
| Provider API changes | Generated code breaks after deployment | Medium | No mitigation in MVP; manual update required |
| Jira API outage | Tickets not created/updated | Low | Queue updates; retry with exponential backoff |
| Credential leakage in logs | Security breach | Low | Explicit credential filtering + audit logging |

### Operational Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| Bottleneck at PM approval gate | Delays pipeline | Medium | Set SLA ≤ 8 hours; escalate if exceeded |
| Invalid test credentials | False negatives on tests | High | User responsibility; warning message if auth fails |
| Deployment without testing | Broken connector in prod | Low | Process requires test completion (not hard gate) |
| Outdated provider docs | Generated code invalid | Medium | Connector + README document source URL + date |

---

## 7. Success Metrics & KPIs

### Primary KPIs

1. **Time to Connector**: Measure end-to-end time from request to deployable code
   - Target: < 4 hours (includes waits for approvals)
   - Baseline: 2-4 weeks (manual approach)

2. **Connector Adoption**: Track how many generated connectors actually deployed
   - Target: ≥ 3 connectors/month deployed by M2 2026
   - Success: Reduces backlog of provider requests

3. **Code Quality**: No critical bugs in generated connectors
   - Target: 100% of connectors pass live testing
   - Tracked via: Test results in Jira

4. **Approval Efficiency**: % of connectors approved without requiring regeneration
   - Target: ≥ 85% approved on first attempt
   - Improves if PM/EM feedback influences prompt refinement

### Secondary KPIs

- **LLM Cost**: Track API spend per connector (target: < $0.01/connector)
- **Session Reliability**: % of sessions completing without crashes (target: ≥ 99%)
- **User Satisfaction**: NPS score from Integration Engineers using the tool (target: ≥ 8/10)

---

## 8. Phased Rollout

### Phase 1 (MVP) — Q2 2026
**Scope**: Single provider connector generation with human approval gates
- [x] 5-step UI wizard
- [x] API discovery (tracking + auth)
- [x] Status mapping with user confirmation
- [x] Code generation + validation
- [x] Live testing with real credentials
- [x] Jira ticket creation & tracking
- [ ] Jira ACL integration (basic)
- **Launch**: Internal beta with 1-2 integration engineers
- **Validation**: Generate 1-2 real connectors, test with actual providers

### Phase 2 (Enhancement) — Q3 2026
**Scope**: Improve accuracy + expand output languages
- [ ] Jira ACL enforcement (role-based approvals)
- [ ] Persistent credential storage (encrypted)
- [ ] Code editing UI (post-generation customization)
- [ ] Support for Java/Go code generation
- [ ] Batch generation (multiple providers in 1 request)
- [ ] Connector versioning & update workflow
- **Target**: 5-10 connectors/month, ≤ 2 hours per connector

### Phase 3 (Scale) — Q4 2026
**Scope**: Automation + self-service
- [ ] Webhook/callback API discovery
- [ ] Automated deployment (CI/CD integration)
- [ ] Connector registry + discovery
- [ ] AI-powered documentation auto-generation
- [ ] Multi-language support maturity
- **Target**: 20+ connectors/month, community submissions

---

## 9. Success Criteria for Launch

MVP is launch-ready when:
- [ ] UI tested end-to-end with 1-2 real provider APIs
- [ ] All LLM calls stay within budget (<$1/connector)
- [ ] Jira tickets created and updated correctly for ≥ 2 test runs
- [ ] Credentials encrypted and securely handled
- [ ] Approval gates working (API → Code → Test → Download)
- [ ] Generated code passes AST validation + live tests
- [ ] Session persistence working (users can refresh without losing state)
- [ ] Documentation (README + TEST_GUIDE) complete
- [ ] Security review completed (credential handling, code execution)
- [ ] Internal beta feedback gathered from 2-3 users

---

## 10. Dependencies & Assumptions

### Dependencies
- Google Gemini 2.5 Flash API (LLM inference)
- Jira Cloud instance (ticket management)
- Public internet access (URL fetching)
- File system storage (connectors)

### Assumptions
- All provider API docs are publicly accessible (no auth required to fetch)
- Provider APIs follow REST conventions (JSON request/response)
- Status codes are documented in API docs (extractable by LLM)
- Users have valid credentials for testing (can't pre-validate)
- Deployment is manual (no auto-CI/CD in MVP)

---

## Appendix A: Jira Ticket Template

```
Summary: Shipping Connector: {Provider Name}

Description:
Provider: {provider_name}
Documentation URL: {docs_url}
Requested By: {user_name}
Created: {timestamp}
Session ID: {session_id}
UI Link: {ui_link} (expires in 24h)

Type: Task
Labels: connector-agent, shipping
Board: RE
Status: In Progress
Assignee: [PM for API review]
```

**Transitions & Checklist**:
- [ ] APIs discovered & reviewed (PM approval)
- [ ] Status mappings confirmed
- [ ] Code generated & reviewed (EM approval)
- [ ] Live testing completed
- [ ] Ready for deployment (download available)
- [ ] Deployed to production (SRE/DevOps)

---

## Appendix B: Connector Directory Structure

```
generated_connectors/
├── delhivery/
│   ├── connector.py (200-400 lines)
│   ├── __init__.py
│   ├── config.json
│   └── README.md
├── xpressbees/
│   ├── connector.py
│   ├── __init__.py
│   ├── config.json
│   └── README.md
└── shiprocket/
    ├── connector.py
    ├── __init__.py
    ├── config.json
    └── README.md
```

**config.json Schema**:
```json
{
  "provider_name": "delhivery",
  "docs_url": "https://...",
  "generated_at": "2026-04-13T10:30:00Z",
  "generated_by": "connector-agent-v1",
  "jira_ticket": "RE-123",
  "tracking_api": {
    "name": "Track Shipment",
    "url": "https://api.delhivery.com/api/shipment/json/",
    "method": "GET",
    "auth_type": "api_key_header"
  },
  "status_mapping": {
    "pending": "Pending",
    "ofd": "Out for Delivery",
    "delivered": "Delivered"
  }
}
```

---

**PRD Version**: 1.0  
**Last Updated**: April 13, 2026  
**Owner**: Product Management / Engineering  
**Status**: Ready for Implementation
