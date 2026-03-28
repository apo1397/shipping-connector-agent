async function generate() {
    const url = document.getElementById('url-input').value.trim();
    if (!url) return alert('Enter URL');

    document.getElementById('input-view').style.display = 'none';
    document.getElementById('progress-view').style.display = 'block';

    const resp = await fetch('/api/v1/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
    });
    const { session_id } = await resp.json();

    const eventSource = new EventSource(`/api/v1/sessions/${session_id}/stream`);
    eventSource.onmessage = (e) => {
        const event = JSON.parse(e.data);
        updateProgress(event);
    };
}

function updateProgress(event) {
    const container = document.getElementById('progress-steps');
    if (event.type === 'step_start') {
        const div = document.createElement('div');
        div.className = 'step running';
        div.id = `step-${event.step}`;
        div.textContent = event.step;
        container.appendChild(div);
    } else if (event.type === 'step_complete') {
        const div = document.getElementById(`step-${event.step}`);
        if (div) {
            div.classList.remove('running');
            div.classList.add('done');
        }
    } else if (event.type === 'step_error') {
        const div = document.getElementById(`step-${event.step}`);
        if (div) {
            div.classList.add('error');
            div.textContent += ` - Error: ${event.error}`;
        }
    }
}

function downloadCode() {
    alert('Download not yet implemented');
}
