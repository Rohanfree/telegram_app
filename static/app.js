// WebSocket Connection and Dashboard Logic

let ws = null;
let filesReceived = 0;
let downloadsCount = 0;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

// DOM Elements
const wsStatusBadge = document.getElementById('ws-status');
const botStatusBadge = document.getElementById('bot-status');

// Status Elements
const currentStateEl = document.getElementById('current-state');
const activeConnectionsEl = document.getElementById('active-connections');
const lastActivityEl = document.getElementById('last-activity');
const filesReceivedEl = document.getElementById('files-received');

// Initialize WebSocket connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    console.log('Connecting to WebSocket:', wsUrl);
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        updateWSStatus('online');
        reconnectAttempts = 0;
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateWSStatus('offline');
    };

    ws.onclose = () => {
        console.log('WebSocket closed');
        updateWSStatus('offline');

        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
            setTimeout(connectWebSocket, delay);
        }
    };
}

// Handle incoming WebSocket messages
function handleMessage(data) {
    updateLastActivity();

    switch (data.type) {
        case 'status':
            updateStatus(data.status, data.details);
            break;

        case 'error':
            console.error('Bot error:', data.error);
            break;

        case 'file_received':
            addFileToDownloads(data.filename, data.file_type, data.file_size, data.username);
            filesReceived++;
            filesReceivedEl.textContent = filesReceived;
            break;

        case 'download_progress':
            updateDownloadProgress(data.filename, data.current_bytes, data.total_bytes, data.pct, data.done);
            break;
    }
}

// Update WebSocket status badge
function updateWSStatus(status) {
    const dot = wsStatusBadge.querySelector('.badge-dot');
    dot.className = 'badge-dot ' + status;
}

// Update bot status
function updateStatus(status, details) {
    currentStateEl.textContent = status.charAt(0).toUpperCase() + status.slice(1);

    const dot = botStatusBadge.querySelector('.badge-dot');
    if (status === 'processing' || status === 'bot_command') {
        dot.className = 'badge-dot online';
    } else if (status === 'completed' || status === 'bot_started') {
        dot.className = 'badge-dot idle';
    } else {
        dot.className = 'badge-dot offline';
    }
}

// Add a file entry to the Downloads panel
function addFileToDownloads(filename, fileType, fileSize, username) {
    const downloadsList = document.getElementById('downloads-list');
    const downloadsEmpty = document.getElementById('downloads-empty');
    const downloadsCountEl = document.getElementById('downloads-count');

    if (downloadsEmpty) downloadsEmpty.style.display = 'none';

    // Avoid duplicate entries (by filename)
    if (document.getElementById('dl-' + CSS.escape(filename))) return;

    const sizeLabel = fileSize > 0 ? formatBytes(fileSize) : '';
    const icon = fileTypeIcon(fileType || '');
    const li = document.createElement('li');
    li.className = 'download-item';
    li.id = 'dl-' + CSS.escape(filename);
    li.innerHTML = `
        <span class="download-icon">${icon}</span>
        <div class="download-info">
            <a class="download-link" href="/downloads/${encodeURIComponent(filename)}" download="${escapeHtml(filename)}">${escapeHtml(filename)}</a>
            <span class="download-meta">${sizeLabel}${username ? ' · ' + escapeHtml(username) : ''}</span>
        </div>
        <button class="view-btn" title="Preview file" onclick="openPreview('${escapeHtml(filename).replace(/'/g, "\\'")}')">▶ View</button>
        <button class="delete-btn" title="Delete file" onclick="deleteFile('${escapeHtml(filename).replace(/'/g, "\\'")}')">Delete</button>
    `;
    downloadsList.insertBefore(li, downloadsList.firstChild);

    downloadsCount++;
    downloadsCountEl.textContent = `${downloadsCount} file${downloadsCount !== 1 ? 's' : ''}`;
}

// ── File Preview Modal ──────────────────────────────────────

let _plyrInstance = null;

function openPreview(filename) {
    const modal = document.getElementById('preview-modal');
    const body = document.getElementById('preview-body');
    const filenameEl = document.getElementById('preview-filename');
    const downloadBtn = document.getElementById('preview-download-btn');

    const streamUrl = `/stream/${encodeURIComponent(filename)}`;
    const downloadUrl = `/downloads/${encodeURIComponent(filename)}`;

    filenameEl.textContent = filename;
    downloadBtn.href = downloadUrl;
    downloadBtn.setAttribute('download', filename);
    body.innerHTML = '';

    const ext = filename.split('.').pop().toLowerCase();
    const videoExts = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v'];
    const audioExts = ['mp3', 'aac', 'flac', 'wav', 'm4a', 'ogg', 'oga', 'opus'];
    const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'];
    const pdfExts = ['pdf'];

    if (videoExts.includes(ext)) {
        // ── Video: use Plyr for rich controls + audio track switching ──
        const video = document.createElement('video');
        video.className = 'preview-video';
        video.controls = true;
        video.crossOrigin = 'anonymous';

        const source = document.createElement('source');
        source.src = streamUrl;
        video.appendChild(source);

        const wrap = document.createElement('div');
        wrap.className = 'preview-video-wrap';
        wrap.appendChild(video);

        // Audio track switcher placeholder (filled after Plyr ready)
        const trackBar = document.createElement('div');
        trackBar.className = 'audio-track-bar';
        trackBar.id = 'audio-track-bar';
        wrap.appendChild(trackBar);

        body.appendChild(wrap);

        // Init Plyr
        if (_plyrInstance) { _plyrInstance.destroy(); _plyrInstance = null; }
        _plyrInstance = new Plyr(video, {
            controls: ['play-large', 'play', 'rewind', 'fast-forward', 'progress',
                'current-time', 'duration', 'mute', 'volume', 'captions',
                'settings', 'pip', 'airplay', 'fullscreen'],
            settings: ['quality', 'speed', 'loop'],
            keyboard: { focused: true, global: true },
            fullscreen: { enabled: true, fallback: true, iosNative: true },
            tooltips: { controls: true, seek: true },
        });

        // Build audio track switcher once metadata is loaded
        video.addEventListener('loadedmetadata', () => {
            buildAudioTrackSwitcher(video, trackBar);
            // Auto-enter fullscreen for video
            _plyrInstance.fullscreen.enter();
        });

    } else if (audioExts.includes(ext)) {
        const wrap = document.createElement('div');
        wrap.className = 'preview-audio-wrap';
        const icon = document.createElement('div');
        icon.className = 'preview-audio-icon';
        icon.textContent = '🎵';
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.src = streamUrl;
        audio.className = 'preview-audio';
        wrap.appendChild(icon);
        wrap.appendChild(audio);
        body.appendChild(wrap);

    } else if (imageExts.includes(ext)) {
        const img = document.createElement('img');
        img.src = streamUrl;
        img.alt = filename;
        img.className = 'preview-image';
        body.appendChild(img);

    } else if (pdfExts.includes(ext)) {
        const frame = document.createElement('iframe');
        frame.src = streamUrl;
        frame.className = 'preview-pdf';
        frame.title = filename;
        body.appendChild(frame);

    } else {
        const div = document.createElement('div');
        div.className = 'preview-unsupported';
        div.innerHTML = `<div style="font-size:3rem">📄</div>
            <p>Cannot preview this file type.</p>
            <a href="${downloadUrl}" download="${escapeHtml(filename)}" class="preview-download-btn" style="display:inline-flex;margin-top:1rem">⬇ Download instead</a>`;
        body.appendChild(div);
    }

    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function buildAudioTrackSwitcher(video, bar) {
    const tracks = video.audioTracks; // HTMLAudioTrackList (Chrome/Edge)
    if (!tracks || tracks.length <= 1) return; // nothing to switch

    bar.innerHTML = '<span class="audio-track-label">🔊 Audio Track:</span>';

    for (let i = 0; i < tracks.length; i++) {
        const t = tracks[i];
        const btn = document.createElement('button');
        btn.className = 'audio-track-btn' + (t.enabled ? ' active' : '');
        btn.textContent = t.label || t.language || `Track ${i + 1}`;
        btn.dataset.index = i;

        btn.addEventListener('click', () => {
            // Disable all tracks, enable selected
            for (let j = 0; j < tracks.length; j++) {
                tracks[j].enabled = (j === i);
            }
            bar.querySelectorAll('.audio-track-btn').forEach((b, j) => {
                b.classList.toggle('active', j === i);
            });
        });

        bar.appendChild(btn);
    }
}

function closePreview() {
    const modal = document.getElementById('preview-modal');
    const body = document.getElementById('preview-body');

    if (_plyrInstance) {
        try { _plyrInstance.fullscreen.exit(); } catch (_) { }
        _plyrInstance.destroy();
        _plyrInstance = null;
    }

    modal.classList.remove('open');
    body.innerHTML = '';
    document.body.style.overflow = '';
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePreview();
});


// ────────────────────────────────────────────────────────────

// Delete a file from the server
async function deleteFile(filename) {
    if (!confirm(`Delete "${filename}" from the server?`)) return;

    try {
        const res = await fetch(`/downloads/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            alert(`Failed to delete: ${err.detail || res.statusText}`);
            return;
        }

        // Remove row from DOM
        const row = document.getElementById('dl-' + CSS.escape(filename));
        if (row) row.remove();

        // Update count
        downloadsCount = Math.max(0, downloadsCount - 1);
        const downloadsCountEl = document.getElementById('downloads-count');
        downloadsCountEl.textContent = `${downloadsCount} file${downloadsCount !== 1 ? 's' : ''}`;

        // Show empty state if no files left
        const list = document.getElementById('downloads-list');
        if (!list || list.children.length === 0) {
            const empty = document.getElementById('downloads-empty');
            if (empty) empty.style.display = '';
        }

        // Update files-received counter in Status panel
        filesReceived = Math.max(0, filesReceived - 1);
        filesReceivedEl.textContent = filesReceived;
    } catch (e) {
        alert('Error deleting file: ' + e.message);
    }
}

// Update (or create) a live progress bar in the Active Downloads panel
const _activeDownloads = {};

function updateDownloadProgress(filename, currentBytes, totalBytes, pct, done) {
    const panel = document.getElementById('active-downloads-panel');
    const content = document.getElementById('active-downloads-content');
    const countEl = document.getElementById('active-downloads-count');
    const safeId = 'adl-' + btoa(filename).replace(/[^a-zA-Z0-9]/g, '');

    if (done) {
        const el = document.getElementById(safeId);
        if (el) el.remove();
        delete _activeDownloads[filename];
        const remaining = Object.keys(_activeDownloads).length;
        countEl.textContent = `${remaining} active`;
        if (remaining === 0) panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';
    _activeDownloads[filename] = pct;
    const remaining = Object.keys(_activeDownloads).length;
    countEl.textContent = `${remaining} active`;

    let el = document.getElementById(safeId);
    if (!el) {
        el = document.createElement('div');
        el.id = safeId;
        el.className = 'active-download-item';
        el.innerHTML = `
            <div class="adl-header">
                <span class="adl-icon">⬇️</span>
                <span class="adl-name">${escapeHtml(filename)}</span>
                <span class="adl-pct" id="${safeId}-pct">0%</span>
            </div>
            <div class="adl-bar-track">
                <div class="adl-bar-fill" id="${safeId}-fill" style="width:0%"></div>
            </div>
            <div class="adl-meta" id="${safeId}-meta">Starting…</div>
        `;
        content.appendChild(el);
    }

    document.getElementById(`${safeId}-pct`).textContent = `${pct}%`;
    document.getElementById(`${safeId}-fill`).style.width = `${pct}%`;
    const mb = (currentBytes / 1048576).toFixed(1);
    const total = totalBytes > 0 ? (totalBytes / 1048576).toFixed(1) + ' MB' : '?';
    document.getElementById(`${safeId}-meta`).textContent = `${mb} MB / ${total}`;
}

// Format bytes to human-readable
function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

// Icon for file type
function fileTypeIcon(type) {
    const icons = { photo: '🖼️', video: '🎬', audio: '🎵', voice: '🎙️', document: '📄' };
    return icons[type] || '📄';
}

// Load existing downloads from server on page load
async function loadExistingDownloads() {
    try {
        const res = await fetch('/downloads');
        const files = await res.json();
        files.forEach(f => addFileToDownloads(f.name, guessFileType(f.name), 0, ''));
    } catch (e) {
        console.warn('Could not load existing downloads:', e);
    }
}

function guessFileType(name) {
    const ext = name.split('.').pop().toLowerCase();
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(ext)) return 'photo';
    if (['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)) return 'video';
    if (['mp3', 'aac', 'flac', 'wav', 'm4a'].includes(ext)) return 'audio';
    if (['ogg', 'oga'].includes(ext)) return 'voice';
    return 'document';
}

// Update last activity
function updateLastActivity() {
    lastActivityEl.textContent = new Date().toLocaleTimeString();
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    loadExistingDownloads();

    // Send ping every 30 seconds to keep connection alive
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
        }
    }, 30000);
});
