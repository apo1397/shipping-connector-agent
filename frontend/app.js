// --- State ---
let sessionId = null;
let currentStep = 1;
let discoveredApis = null;
let mappings = [];
let generatedFiles = {};
let authMechanism = 'none';

const GOKWIK_STATUSES = [
    'order_placed','pickup_pending','pickup_scheduled','out_for_pickup','picked_up',
    'in_transit','reached_destination_hub','out_for_delivery','delivered',
    'delivery_failed','delivery_failed_customer_unavailable','delivery_failed_address_issue',
    'delivery_failed_refused','rto_initiated','rto_in_transit','rto_delivered',
    'cancelled','lost','damaged','on_hold','unknown'
];

// --- Step Navigation ---
function showStep(num) {
    document.querySelectorAll('.step-section').forEach(el => el.classList.add('hidden'));
    document.getElementById(`step-${num}`).classList.remove('hidden');
    document.querySelectorAll('.step-indicator').forEach(el => {
        const s = parseInt(el.dataset.step);
        el.classList.remove('active', 'complete');
        if (s < num) el.classList.add('complete');
        else if (s === num) el.classList.add('active');
    });
    document.querySelectorAll('.step-line').forEach((el, i) => {
        el.classList.toggle('active', i < num - 1);
    });
    currentStep = num;
}

function showProgress(msg) {
    document.getElementById('progress-log').classList.remove('hidden');
    document.getElementById('progress-message').textContent = msg;
}

function hideProgress() {
    document.getElementById('progress-log').classList.add('hidden');
}

function showError(msg) {
    const banner = document.getElementById('error-banner');
    document.getElementById('error-text').textContent = msg;
    banner.classList.remove('hidden');
    setTimeout(() => banner.classList.add('hidden'), 10000);
}

// --- Step 1: Start Analysis ---
async function startAnalysis() {
    const url = document.getElementById('url-input').value.trim();
    if (!url) return showError('Please enter a documentation URL');

    const provider = document.getElementById('provider-input').value.trim();
    const btn = document.getElementById('analyze-btn');
    btn.disabled = true;
    btn.textContent = 'Analyzing...';
    showProgress('Creating session...');

    try {
        const resp = await fetch('/api/v1/sessions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url, provider_name_hint: provider || null})
        });
        const data = await resp.json();
        sessionId = data.session_id;
        connectSSE(sessionId);
    } catch (e) {
        showError('Failed to create session: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Analyze Documentation';
    }
}

// --- SSE Connection ---
function connectSSE(sid) {
    const es = new EventSource(`/api/v1/sessions/${sid}/stream`);
    es.onmessage = (e) => {
        const event = JSON.parse(e.data);
        handleSSEEvent(event);
    };
    es.onerror = () => {
        hideProgress();
    };
}

function handleSSEEvent(event) {
    switch (event.type) {
        case 'step_start':
            showProgress(event.message || `Running: ${event.step}...`);
            break;
        case 'step_complete':
            handleStepComplete(event);
            break;
        case 'step_error':
            hideProgress();
            showError(`Error in ${event.step}: ${event.error}`);
            break;
        case 'mapping_review':
            hideProgress();
            mappings = event.mappings;
            renderMappingTable(mappings);
            showStep(3);
            break;
        case 'test_ready':
            hideProgress();
            break;
    }
}

function handleStepComplete(event) {
    const step = event.step;
    if (step === 'discover_apis' && event.data) {
        discoveredApis = event.data;
        authMechanism = event.data.auth_mechanism || 'none';
        renderApiCards(event.data);
        hideProgress();
        showStep(2);
    } else if (step === 'generate_code' && event.data) {
        generatedFiles = event.data.files || {};
        renderCodeTabs(generatedFiles);
        if (event.data.validation_errors && event.data.validation_errors.length > 0) {
            showValidationWarnings(event.data.validation_errors);
        }
        hideProgress();
        showStep(4);
    }
}

// --- Step 2: Render API Cards ---
function renderApiCards(data) {
    renderEndpointCard('tracking-api-details', data.tracking_api);
    const conf = data.tracking_api?.confidence || 0;
    const confEl = document.getElementById('tracking-confidence');
    confEl.textContent = `${Math.round(conf * 100)}% confidence`;
    confEl.className = 'confidence-badge ' + (conf >= 0.7 ? 'confidence-high' : conf >= 0.4 ? 'confidence-medium' : 'confidence-low');

    if (data.auth_api) {
        renderEndpointCard('auth-api-details', data.auth_api);
        document.getElementById('auth-type-badge').textContent = data.auth_api.auth_type || 'none';
    } else {
        document.getElementById('auth-api-details').innerHTML = '<p class="text-gray-500 text-sm">No dedicated auth endpoint — uses static API key or headers.</p>';
        document.getElementById('auth-type-badge').textContent = 'none';
    }
}

function renderEndpointCard(containerId, endpoint) {
    if (!endpoint) return;
    const c = document.getElementById(containerId);
    const rows = [
        ['Method', `<span class="method-badge method-${endpoint.method}">${endpoint.method}</span>`],
        ['URL', `<code class="text-sm bg-gray-100 px-2 py-1 rounded">${endpoint.url}</code>`],
        ['Headers', endpoint.headers && Object.keys(endpoint.headers).length > 0
            ? `<pre class="text-xs bg-gray-50 p-2 rounded">${JSON.stringify(endpoint.headers, null, 2)}</pre>` : '<span class="text-gray-400">None</span>'],
        ['AWB Field', endpoint.awb_field_name ? `<code>${endpoint.awb_field_name}</code>` : '<span class="text-gray-400">N/A</span>'],
    ];
    if (endpoint.request_body) {
        rows.push(['Request Body', `<pre class="text-xs bg-gray-50 p-2 rounded max-h-32 overflow-auto">${JSON.stringify(endpoint.request_body, null, 2)}</pre>`]);
    }
    if (endpoint.query_params) {
        rows.push(['Query Params', `<pre class="text-xs bg-gray-50 p-2 rounded">${JSON.stringify(endpoint.query_params, null, 2)}</pre>`]);
    }
    if (endpoint.response_schema) {
        rows.push(['Response', `<pre class="text-xs bg-gray-50 p-2 rounded max-h-40 overflow-auto">${JSON.stringify(endpoint.response_schema, null, 2)}</pre>`]);
    }
    if (endpoint.reasoning) {
        rows.push(['Reasoning', `<span class="text-sm text-gray-600">${endpoint.reasoning}</span>`]);
    }
    c.innerHTML = rows.map(([label, value]) =>
        `<div class="detail-row"><div class="detail-label">${label}</div><div class="detail-value">${value}</div></div>`
    ).join('');
}

function continueToMapping() {
    showStep(3);
    showProgress('Waiting for status extraction and mapping...');
    // Pipeline continues in background — mapping_review event will trigger renderMappingTable
    if (mappings.length > 0) {
        hideProgress();
    }
}

// --- Step 3: Mapping Table ---
function renderMappingTable(statuses) {
    const tbody = document.getElementById('mapping-table-body');
    tbody.innerHTML = statuses.map((s, i) => {
        const options = GOKWIK_STATUSES.map(gs =>
            `<option value="${gs}" ${gs === s.suggested_mapping ? 'selected' : ''}>${gs}</option>`
        ).join('');
        return `<tr class="border-b border-gray-100">
            <td class="py-3 px-2 font-mono text-sm">${s.code}</td>
            <td class="py-3 px-2 text-sm text-gray-600">${s.description}</td>
            <td class="py-3 px-2"><span class="text-xs px-2 py-1 rounded ${s.is_terminal ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}">${s.is_terminal ? 'Yes' : 'No'}</span></td>
            <td class="py-3 px-2"><select class="mapping-select" data-code="${s.code}">${options}</select></td>
        </tr>`;
    }).join('');
}

async function confirmMappings() {
    const selects = document.querySelectorAll('.mapping-select');
    const confirmed = {};
    selects.forEach(sel => { confirmed[sel.dataset.code] = sel.value; });

    const btn = document.getElementById('confirm-btn');
    btn.disabled = true;
    btn.textContent = 'Generating code...';
    showProgress('Generating connector code...');

    try {
        await fetch(`/api/v1/sessions/${sessionId}/mappings`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mappings: confirmed})
        });
        // Code generation will complete via SSE → step_complete for generate_code
    } catch (e) {
        showError('Failed to confirm mappings: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Confirm Mappings & Generate Code';
    }
}

// --- Step 4: Code Display ---
function renderCodeTabs(files) {
    const tabsContainer = document.getElementById('code-tabs');
    const display = document.getElementById('code-display');
    const filenames = Object.keys(files);
    if (filenames.length === 0) return;

    tabsContainer.innerHTML = filenames.map((fn, i) =>
        `<button class="code-tab ${i === 0 ? 'active' : ''}" onclick="switchCodeTab('${fn}')">${fn}</button>`
    ).join('');

    switchCodeTab(filenames[0]);
}

function switchCodeTab(filename) {
    document.querySelectorAll('.code-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.code-tab').forEach(t => { if (t.textContent === filename) t.classList.add('active'); });

    const code = generatedFiles[filename] || '';
    const lang = filename.endsWith('.json') ? 'json' : 'python';
    const highlighted = Prism.highlight(code, Prism.languages[lang], lang);
    document.getElementById('code-display').innerHTML = `<pre class="!m-0 !rounded-lg"><code class="language-${lang}">${highlighted}</code></pre>`;
}

function showValidationWarnings(errors) {
    const el = document.getElementById('validation-warnings');
    el.classList.remove('hidden');
    el.innerHTML = `<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
        <p class="text-yellow-800 text-sm font-medium mb-1">Validation Warnings</p>
        ${errors.map(e => `<p class="text-yellow-700 text-xs">- ${e}</p>`).join('')}
    </div>`;
}

async function downloadCode() {
    if (!sessionId) return;
    window.location.href = `/api/v1/sessions/${sessionId}/download`;
}

function goToTest() {
    renderCredentialFields();
    showStep(5);
}

// --- Step 5: Live Test ---
function renderCredentialFields() {
    const container = document.getElementById('credential-fields');
    let fields = '';
    if (authMechanism === 'bearer_token' || authMechanism === 'api_key_header') {
        fields = `<div><label class="block text-sm font-medium text-gray-700 mb-1">API Key / Token</label>
            <input type="text" id="cred-api-key" placeholder="Enter API key or token"
                   class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"></div>`;
    } else if (authMechanism === 'basic') {
        fields = `<div class="grid grid-cols-2 gap-4">
            <div><label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
                <input type="text" id="cred-username" class="w-full px-4 py-3 border border-gray-300 rounded-lg"></div>
            <div><label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input type="password" id="cred-password" class="w-full px-4 py-3 border border-gray-300 rounded-lg"></div>
        </div>`;
    } else if (authMechanism === 'oauth2') {
        fields = `<div class="grid grid-cols-2 gap-4">
            <div><label class="block text-sm font-medium text-gray-700 mb-1">Client ID</label>
                <input type="text" id="cred-client-id" class="w-full px-4 py-3 border border-gray-300 rounded-lg"></div>
            <div><label class="block text-sm font-medium text-gray-700 mb-1">Client Secret</label>
                <input type="password" id="cred-client-secret" class="w-full px-4 py-3 border border-gray-300 rounded-lg"></div>
        </div>`;
    } else {
        fields = `<div><label class="block text-sm font-medium text-gray-700 mb-1">Credentials (JSON)</label>
            <textarea id="cred-json" rows="3" placeholder='{"api_key": "..."}'
                      class="w-full px-4 py-3 border border-gray-300 rounded-lg font-mono text-sm"></textarea></div>`;
    }
    container.innerHTML = fields;
}

function collectCredentials() {
    if (authMechanism === 'bearer_token' || authMechanism === 'api_key_header') {
        return {api_key: document.getElementById('cred-api-key')?.value || ''};
    } else if (authMechanism === 'basic') {
        return {username: document.getElementById('cred-username')?.value || '', password: document.getElementById('cred-password')?.value || ''};
    } else if (authMechanism === 'oauth2') {
        return {client_id: document.getElementById('cred-client-id')?.value || '', client_secret: document.getElementById('cred-client-secret')?.value || ''};
    } else {
        try { return JSON.parse(document.getElementById('cred-json')?.value || '{}'); } catch { return {}; }
    }
}

async function runTest() {
    const credentials = collectCredentials();
    const awbText = document.getElementById('awb-input').value.trim();
    if (!awbText) return showError('Enter at least one AWB number');

    const awb_numbers = awbText.split(',').map(s => s.trim()).filter(Boolean);
    const btn = document.getElementById('test-btn');
    btn.disabled = true;
    btn.textContent = 'Testing...';

    try {
        const resp = await fetch(`/api/v1/sessions/${sessionId}/test`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({credentials, awb_numbers})
        });
        const data = await resp.json();
        renderTestResults(data.results || []);
    } catch (e) {
        showError('Test failed: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run Test';
    }
}

function renderTestResults(results) {
    const container = document.getElementById('test-results');
    const body = document.getElementById('test-results-body');
    container.classList.remove('hidden');

    body.innerHTML = results.map(r => {
        const cls = r.success ? 'success' : 'failure';
        const badge = r.success
            ? '<span class="text-xs px-2 py-1 bg-green-100 text-green-700 rounded-full font-medium">PASS</span>'
            : '<span class="text-xs px-2 py-1 bg-red-100 text-red-700 rounded-full font-medium">FAIL</span>';
        let details = '';
        if (r.success && r.result) {
            details = `<pre class="text-xs bg-gray-50 p-3 rounded mt-2 max-h-48 overflow-auto">${JSON.stringify(r.result, null, 2)}</pre>`;
        } else if (r.error) {
            details = `<p class="text-red-600 text-sm mt-1">${r.error}</p>`;
        }
        if (r.raw_response) {
            details += `<details class="mt-2"><summary class="text-xs text-gray-500 cursor-pointer">Raw Response</summary>
                <pre class="text-xs bg-gray-50 p-3 rounded mt-1 max-h-48 overflow-auto">${JSON.stringify(r.raw_response, null, 2)}</pre></details>`;
        }
        return `<div class="test-result-card ${cls}">
            <div class="flex items-center justify-between">
                <span class="font-mono text-sm font-medium">${r.awb}</span>
                ${badge}
            </div>
            ${details}
        </div>`;
    }).join('');
}
