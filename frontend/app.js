// ─── State ──────────────────────────────────────────────────────────────
let sessionId = null;
let providerName = '';
let requestor = '@requestor';
let authApiData = null;
let trackingApiData = null;
let providerStatuses = [];
let connectorConfig = null;
let approvalContext = null;

const GOKWIK_STATUSES = [
    'order_placed','pickup_pending','pickup_scheduled','out_for_pickup','picked_up',
    'in_transit','reached_destination_hub','out_for_delivery','delivered',
    'delivery_failed','delivery_failed_customer_unavailable','delivery_failed_address_issue',
    'delivery_failed_refused','rto_initiated','rto_in_transit','rto_delivered',
    'cancelled','lost','damaged','on_hold','unknown'
];

// ─── Helpers ────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const show = (id) => $(id).classList.remove('hidden');
const hide = (id) => $(id).classList.add('hidden');

function setState(text, color = 'gray') {
    const pill = $('state-pill');
    pill.textContent = text;
    pill.className = `px-2.5 py-1 rounded-full bg-${color}-100 text-${color}-700`;
}

function setJira(ticket) {
    if (!ticket) return;
    const pill = $('jira-pill');
    pill.textContent = `JIRA: ${ticket}`;
    pill.classList.remove('hidden');
}

function showError(msg) {
    $('error-text').textContent = msg;
    show('error-banner');
    setTimeout(() => hide('error-banner'), 8000);
}

function formatFieldLabel(field) {
    return field.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// ─── Notification feed rendering ────────────────────────────────────────
function appendNotification(n) {
    const empty = $('feed-empty');
    if (empty) empty.remove();

    const feed = $('feed');
    const node = document.createElement('div');
    node.className = `feed-item feed-status-${n.status}`;

    const icon = ({
        started: '⋯',
        passed: '✓',
        failed: '✗',
        needs_input: '?',
    })[n.status] || '·';

    const ts = new Date(n.ts).toLocaleTimeString();
    const jiraTag = n.jira && n.jira !== 'not yet created'
        ? `<span class="feed-jira">${n.jira}</span>`
        : '';

    node.innerHTML = `
        <div class="feed-icon">${icon}</div>
        <div class="feed-body">
            <div class="feed-line">
                <span class="feed-step">${n.step}</span>
                <span class="feed-status">${n.status}</span>
                <span class="feed-by">by ${n.by}</span>
                ${jiraTag}
                <span class="feed-ts">${ts}</span>
            </div>
            ${n.details ? `<div class="feed-details">${n.details}</div>` : ''}
        </div>`;
    feed.appendChild(node);
    feed.scrollTop = feed.scrollHeight;

    const count = feed.querySelectorAll('.feed-item').length;
    $('feed-count').textContent = `${count} event${count === 1 ? '' : 's'}`;
}

// ─── Panel switching ────────────────────────────────────────────────────
function showPanel(name) {
    ['submit', 'clarify', 'staging', 'test', 'approval', 'config']
        .forEach(p => hide(`panel-${p}`));
    show(`panel-${name}`);
}

// ─── Step 1: Submit ─────────────────────────────────────────────────────
async function startAnalysis() {
    const url = $('url-input').value.trim();
    if (!url) return showError('Documentation URL is required');
    providerName = $('provider-input').value.trim();
    requestor = ($('requestor-input').value.trim() || '@requestor');
    if (!requestor.startsWith('@')) requestor = '@' + requestor;

    const btn = $('analyze-btn');
    btn.disabled = true;
    btn.textContent = 'Submitting...';
    hide('dedup-warning');

    try {
        const resp = await fetch('/api/v1/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url,
                provider_name_hint: providerName || null,
                requestor,
            }),
        });

        if (resp.status === 409) {
            const data = await resp.json();
            $('dedup-warning').innerHTML = `
                <strong>Duplicate request blocked.</strong><br>
                ${data.message}<br>
                Prior provider: <code>${data.prior_provider}</code><br>
                Prior URL: <code>${data.prior_url}</code>
            `;
            show('dedup-warning');
            btn.disabled = false;
            btn.textContent = 'Submit request';
            return;
        }

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        sessionId = data.session_id;
        setState('Pre-flight', 'blue');
        connectSSE(sessionId);
        // Hide submit panel; the feed + subsequent panels take over
        hide('panel-submit');
    } catch (e) {
        showError('Failed to submit: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Submit request';
    }
}

// ─── SSE handling ───────────────────────────────────────────────────────
function connectSSE(sid) {
    const es = new EventSource(`/api/v1/sessions/${sid}/stream`);
    es.onmessage = (e) => {
        try {
            const event = JSON.parse(e.data);
            handleSSE(event);
        } catch (err) {
            console.warn('SSE parse error:', err);
        }
    };
    es.onerror = () => {
        console.warn('SSE connection closed');
    };
}

function handleSSE(event) {
    console.log('[SSE]', event.type, event);
    switch (event.type) {
        case 'notification':
            appendNotification(event);
            break;

        case 'preflight_duplicate':
            setState('Blocked — duplicate', 'red');
            showError('Duplicate request: ' + event.message);
            break;

        case 'clarification_needed':
            setState('Clarify endpoint', 'amber');
            renderClarification(event);
            break;

        case 'staging_url_flagged':
            setState('Confirm prod URL', 'orange');
            $('staging-discovered').textContent = event.discovered_url;
            showPanel('staging');
            break;

        case 'staging_url_resolved':
            setState('Awaiting creds', 'blue');
            // The next event (awaiting_creds_and_awb) will populate the test panel
            break;

        case 'awaiting_creds_and_awb':
            authApiData = event.auth;
            renderCredFields(event.auth, event.credentials_required);
            setState('Awaiting creds + AWB', 'blue');
            showPanel('test');
            break;

        case 'validations_passed':
            setJira(event.jira_ticket);
            break;

        case 'validations_failed':
            // Diagnosis already rendered by runLiveTest()'s response
            setState('Test failed — retry', 'red');
            break;

        case 'awaiting_approval':
            approvalContext = event;
            renderApproval(event);
            setState('Awaiting approval', 'amber');
            showPanel('approval');
            break;

        case 'rejected':
            setState('Rejected', 'red');
            break;

        case 'step_complete':
            if (event.step === 'discover_apis' && event.data) {
                trackingApiData = event.data.tracking_api;
                authApiData = event.data.auth_api;
                providerStatuses = event.data.provider_statuses || [];
            }
            if (event.step === 'generate_config' && event.data) {
                connectorConfig = event.data.config;
                renderConfig(connectorConfig);
                setState('Done — handed off', 'green');
                showPanel('config');
            }
            break;

        case 'config_ready':
            // No-op; rendering already done on step_complete
            break;

        case 'step_error':
            showError(`${event.step}: ${event.error}`);
            setState('Error', 'red');
            break;
    }
}

// ─── Clarification panel ────────────────────────────────────────────────
function renderClarification(event) {
    $('clarify-question').textContent = event.question || '';
    const opts = (event.candidates || []).map((c, i) => `
        <label class="flex items-start gap-2 p-2 bg-white rounded border border-amber-200 cursor-pointer hover:bg-amber-50">
            <input type="radio" name="candidate" value="${i}" class="mt-0.5" ${i === 0 ? 'checked' : ''}>
            <div class="text-xs">
                <div class="font-medium text-gray-900">${c.name || ('Option ' + (i+1))}</div>
                <div class="text-gray-600 mt-0.5">${c.description || ''}</div>
                <code class="text-blue-700">${c.method || ''} ${c.url || ''}</code>
            </div>
        </label>`).join('');
    $('clarify-options').innerHTML = opts;
    showPanel('clarify');
}

async function submitClarification() {
    const checked = document.querySelector('input[name="candidate"]:checked');
    const idx = checked ? parseInt(checked.value) : 0;
    const btn = $('clarify-btn');
    btn.disabled = true;
    btn.textContent = 'Applying...';
    try {
        await fetch(`/api/v1/sessions/${sessionId}/clarification`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ candidate_index: idx, focus_hint: '' }),
        });
        hide('panel-clarify');
        setState('Discovering', 'blue');
    } catch (e) {
        showError('Clarification failed: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Use selected endpoint';
    }
}

// ─── Staging URL panel ──────────────────────────────────────────────────
async function submitProdUrl() {
    const url = $('prod-url-input').value.trim();
    if (!url) return showError('Production base URL is required');
    const btn = $('prod-url-btn');
    btn.disabled = true;
    btn.textContent = 'Confirming...';
    try {
        const resp = await fetch(`/api/v1/sessions/${sessionId}/prod-url`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prod_base_url: url }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        // The server will fire the next SSE event (awaiting_creds_and_awb)
    } catch (e) {
        showError('Prod URL submit failed: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Confirm prod URL';
    }
}

// ─── Test panel ─────────────────────────────────────────────────────────
function renderCredFields(auth, credsRequired) {
    const fields = (credsRequired && credsRequired.length) ? credsRequired
        : (auth?.credentials_required?.length ? auth.credentials_required : ['api_key']);
    const guideText = auth?.how_to_get_credentials;
    if (guideText) {
        $('cred-guide').textContent = guideText;
        show('cred-guide');
    }
    $('credential-fields').innerHTML = fields.map(f => {
        const isSecret = /password|secret|token|key/i.test(f);
        return `
            <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">${formatFieldLabel(f)}</label>
                <input type="${isSecret ? 'password' : 'text'}" id="cred-${f}"
                       placeholder="${f}"
                       class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 font-mono">
            </div>`;
    }).join('');
}

async function runLiveTest() {
    if (!sessionId) return showError('No active session');

    const fields = authApiData?.credentials_required?.length
        ? authApiData.credentials_required : ['api_key'];
    const credentials = {};
    const missing = [];
    fields.forEach(f => {
        const v = $(`cred-${f}`)?.value.trim();
        if (v) credentials[f] = v; else missing.push(formatFieldLabel(f));
    });
    if (missing.length) return showError(`Missing: ${missing.join(', ')}`);

    const awb = $('awb-input').value.trim();
    if (!awb) return showError('AWB number is required');

    const btn = $('test-btn');
    btn.disabled = true;
    btn.textContent = 'Testing...';
    hide('test-diagnosis');

    try {
        const resp = await fetch(`/api/v1/sessions/${sessionId}/test-endpoint`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credentials, awb_number: awb }),
        });
        const result = await resp.json();
        renderTestDiagnosis(result);
    } catch (e) {
        showError('Test failed: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run live test';
    }
}

function renderTestDiagnosis(result) {
    const cls = result.classification || { classification: 'unknown' };
    const passed = cls.classification === 'passed';
    const colors = passed
        ? 'bg-green-50 border-green-200 text-green-900'
        : 'bg-red-50 border-red-200 text-red-900';

    const node = $('test-diagnosis');
    node.className = `mt-4 p-3 rounded-lg border text-xs ${colors}`;

    const action = cls.requestor_action
        ? `<div class="mt-2 font-medium">Action: ${cls.requestor_action}</div>` : '';
    const status = result.current_status
        ? `<div class="mt-1">Detected status: <code>${result.current_status}</code></div>` : '';
    const errLine = result.error
        ? `<details class="mt-2"><summary class="cursor-pointer">Error detail</summary><pre class="text-xs mt-1 whitespace-pre-wrap">${result.error}</pre></details>` : '';
    const rawLine = result.tracking_response
        ? `<details class="mt-1"><summary class="cursor-pointer">Raw response</summary><pre class="text-xs mt-1 max-h-40 overflow-auto bg-white rounded p-2 border">${JSON.stringify(result.tracking_response, null, 2)}</pre></details>` : '';

    node.innerHTML = `
        <div class="font-semibold">${passed ? '✓ Passed' : '✗ ' + cls.classification}</div>
        <div class="mt-1">${cls.reason || ''}</div>
        ${status}${action}${errLine}${rawLine}
    `;
    show('test-diagnosis');
}

// ─── Approval panel ─────────────────────────────────────────────────────
function renderApproval(ev) {
    const tracking = ev.tracking_api || {};
    const auth = ev.auth_api || {};
    const test = ev.test_result || {};
    const mappings = ev.mappings || [];

    $('approval-jira').textContent = ev.jira_ticket_id || '';

    $('approval-summary').innerHTML = `
        <div class="bg-gray-50 rounded p-2">
            <div class="text-gray-500 uppercase text-[10px] font-semibold mb-0.5">Endpoint</div>
            <div class="font-mono text-gray-900">${tracking.method || '?'} ${tracking.url || '?'}</div>
            ${ev.host_rewritten ? `<div class="text-orange-700 mt-1">Host rewritten from staging: <code>${ev.discovered_host_original || ''}</code></div>` : ''}
        </div>
        <div class="bg-gray-50 rounded p-2">
            <div class="text-gray-500 uppercase text-[10px] font-semibold mb-0.5">Auth</div>
            <div>${auth.auth_type || 'unknown'}</div>
        </div>
        <div class="bg-gray-50 rounded p-2">
            <div class="text-gray-500 uppercase text-[10px] font-semibold mb-0.5">Test result</div>
            <div>AWB <code>${test.tracking_response ? '—' : ''}</code> · status <code>${test.current_status || '—'}</code> · ${test.duration_ms || 0}ms</div>
        </div>
        <div class="bg-gray-50 rounded p-2">
            <div class="text-gray-500 uppercase text-[10px] font-semibold mb-0.5">Mappings</div>
            <div>${mappings.length} provider statuses</div>
        </div>
    `;

    // Mapping table
    const tbody = $('approval-mapping-body');
    tbody.innerHTML = mappings.map(s => {
        const opts = GOKWIK_STATUSES.map(g =>
            `<option value="${g}" ${g === s.suggested_mapping ? 'selected' : ''}>${g}</option>`
        ).join('');
        return `<tr class="border-t border-gray-100">
            <td class="py-1 px-2 font-mono">${s.code}</td>
            <td class="py-1 px-2 text-gray-600">${s.description || ''}</td>
            <td class="py-1 px-2"><span class="${s.is_terminal ? 'text-red-700' : 'text-gray-500'}">${s.is_terminal ? 'Yes' : 'No'}</span></td>
            <td class="py-1 px-2"><select class="approval-mapping-select text-xs border border-gray-200 rounded" data-code="${s.code}">${opts}</select></td>
        </tr>`;
    }).join('');
}

async function submitApproval(decision) {
    const comment = $('approval-comment').value.trim();
    if (decision === 'reject' && !comment) {
        return showError('A comment is required to reject');
    }

    const confirmedMappings = {};
    document.querySelectorAll('.approval-mapping-select').forEach(s => {
        confirmedMappings[s.dataset.code] = s.value;
    });

    const btn = decision === 'approve' ? $('approve-btn') : $('reject-btn');
    btn.disabled = true;
    btn.textContent = decision === 'approve' ? 'Approving...' : 'Rejecting...';

    try {
        await fetch(`/api/v1/sessions/${sessionId}/approval`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                decision,
                comment: comment || null,
                approver: requestor,
                confirmed_mappings: confirmedMappings,
            }),
        });
        hide('panel-approval');
    } catch (e) {
        showError('Approval failed: ' + e.message);
        btn.disabled = false;
        btn.textContent = decision === 'approve' ? 'Approve & handoff' : 'Reject';
    }
}

// ─── Final config render ────────────────────────────────────────────────
function renderConfig(config) {
    const auth = config.authentication || {};
    const tracking = config.tracking?.endpoint || {};
    const statusMap = config.status_map || [];
    const testRun = config.test_run || {};

    $('config-summary').innerHTML = `
        <div class="bg-blue-50 rounded p-2 border border-blue-100">
            <div class="text-blue-600 uppercase text-[10px] font-semibold">Auth</div>
            <div class="font-bold text-blue-900">${auth.type || 'unknown'}</div>
        </div>
        <div class="bg-green-50 rounded p-2 border border-green-100">
            <div class="text-green-600 uppercase text-[10px] font-semibold">Tracking</div>
            <div class="font-bold text-green-900">${tracking.method || '?'} ${tracking.path || tracking.url || '—'}</div>
        </div>
        <div class="bg-purple-50 rounded p-2 border border-purple-100">
            <div class="text-purple-600 uppercase text-[10px] font-semibold">Statuses</div>
            <div class="font-bold text-purple-900">${statusMap.length} mapped · ${statusMap.filter(s => s.is_terminal).length} terminal</div>
        </div>
        <div class="bg-orange-50 rounded p-2 border border-orange-100">
            <div class="text-orange-600 uppercase text-[10px] font-semibold">Live test</div>
            <div class="font-bold text-orange-900">${testRun.outcome?.success ? '✓ Passed' : '✗ ' + (testRun.outcome?.stage_reached || 'failed')}</div>
        </div>
    `;

    const jsonStr = JSON.stringify(config, null, 2);
    const highlighted = Prism.highlight(jsonStr, Prism.languages.json, 'json');
    $('config-display').innerHTML =
        `<pre class="!m-0 !rounded-lg p-3 text-xs leading-relaxed"><code class="language-json">${highlighted}</code></pre>`;
}

async function copyConfig() {
    if (!connectorConfig) return;
    await navigator.clipboard.writeText(JSON.stringify(connectorConfig, null, 2));
    const btn = $('copy-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
}

async function downloadConfig() {
    if (!sessionId) return;
    window.location.href = `/api/v1/sessions/${sessionId}/download`;
}
