import {
  startCamera, stopCamera, captureFrame, getGPS, seedGPS,
  connectWebSocket, disconnectWebSocket, sendMessage, isConnected,
} from './camera.js';
import { speakNarration, stopSpeaking, toggleMute, isMuted, startListening, stopListening, unlockAudio } from './audio.js';
import { renderARLabels, clearARLabels, showSubtitle, hideSubtitle } from './overlay.js';

// ── State machine ──

const State = Object.freeze({
  IDLE: 'IDLE',
  ANALYZING: 'ANALYZING',
  INSPECTING: 'INSPECTING',
  REPORT: 'REPORT',
});

let currentState = State.IDLE;
let frameInterval = null;
let sessionId = crypto.randomUUID().slice(0, 8);
let pausedFrameDataUrl = null;
let sessionStartTime = null;
let gpsDisplayRAF = null;
let awaitingResponse = false;

// ── Screen loading ──

const screenCache = {};

async function loadScreen(name) {
  if (screenCache[name]) return screenCache[name];
  const res = await fetch(`screens/${name}.html`);
  if (!res.ok) throw new Error(`Failed to load screen: ${name}`);
  const html = await res.text();
  screenCache[name] = html;
  return html;
}

function showScreen(id) {
  document.querySelectorAll('#app > [id^="screen-"]').forEach(el => {
    el.classList.add('hidden');
    el.style.opacity = '0';
  });
  const target = document.getElementById(id);
  if (!target) return;
  target.classList.remove('hidden');
  // Force reflow then fade in
  void target.offsetHeight;
  requestAnimationFrame(() => {
    target.style.opacity = '1';
  });
}

// ── Session timer ──

function getSessionDuration() {
  if (!sessionStartTime) return '0m 0s';
  const diff = Math.floor((Date.now() - sessionStartTime) / 1000);
  const min = Math.floor(diff / 60);
  const sec = diff % 60;
  return `${min}m ${sec.toString().padStart(2, '0')}s`;
}

// ── WebSocket message handler ──

function handleWSMessage(data) {
  awaitingResponse = false;
  setLoading(false);

  switch (data.type) {
    case 'narration':
      if (currentState === State.ANALYZING) {
        speakNarration(data.text);
        if (data.ar_labels?.length) renderARLabels(data.ar_labels);
      }
      break;

    case 'layer_data':
      if (currentState === State.INSPECTING) {
        hideInspectorLoading();
        populateLayerInspector(data);
      }
      break;

    case 'report':
      sessionId = data.report_id || sessionId;
      transitionTo(State.REPORT, data);
      break;

    case 'gps_required':
      showGPSOverlay();
      break;

    case 'error':
      console.error('[WS] Backend error:', data.message);
      showSubtitle(`Error: ${data.message || 'Something went wrong'}`);
      break;
  }
}

function handleWSDisconnect() {
  if (currentState === State.ANALYZING) {
    showSubtitle('Connection lost — reconnecting...');
  }
}

function handleWSReconnect() {
  if (currentState === State.ANALYZING) {
    hideSubtitle();
  }
}

// ── Loading indicator ──

function setLoading(show) {
  const el = document.getElementById('loading-indicator');
  if (!el) return;
  el.classList.toggle('hidden', !show);
}

function hideInspectorLoading() {
  const el = document.getElementById('inspector-loading');
  if (el) el.classList.add('hidden');
  // Reveal the data cards with staggered animation
  const cards = ['card-zoning', 'card-environment', 'card-safety', 'card-311'];
  cards.forEach((id, i) => {
    const card = document.getElementById(id);
    if (!card) return;
    card.style.opacity = '0';
    card.style.transform = 'translateY(12px)';
    card.style.transition = 'opacity 400ms ease, transform 400ms ease';
    card.classList.remove('hidden');
    setTimeout(() => {
      card.style.opacity = '1';
      card.style.transform = 'translateY(0)';
    }, 100 * i);
  });
}

// ── Frame capture loop ──

let framesPaused = false;  // pause frames while user is talking

function pauseFrames() { framesPaused = true; }
function resumeFrames() { framesPaused = false; }

function startFrameLoop() {
  stopFrameLoop();
  frameInterval = setInterval(() => {
    if (awaitingResponse || framesPaused) return;
    const gps = getGPS();
    if (!gps) return;
    const imageB64 = captureFrame();
    if (!imageB64) return;

    sendMessage({
      type: 'frame',
      image_b64: imageB64,
      gps: { lat: gps.lat, lng: gps.lng },
    });

    awaitingResponse = true;
    setLoading(true);
  }, 2000);
}

function stopFrameLoop() {
  if (frameInterval) {
    clearInterval(frameInterval);
    frameInterval = null;
  }
  awaitingResponse = false;
}

// ── State transitions ──

async function transitionTo(newState, payload = null) {
  await cleanup(currentState);
  currentState = newState;

  switch (newState) {
    case State.IDLE:
      showScreen('screen-idle');
      resetSession();
      break;

    case State.ANALYZING:
      await enterAnalyzing();
      break;

    case State.INSPECTING:
      await enterInspecting();
      break;

    case State.REPORT:
      await enterReport(payload);
      break;
  }
}

async function cleanup(state) {
  switch (state) {
    case State.ANALYZING:
      stopFrameLoop();
      clearARLabels();
      hideSubtitle();
      stopSpeaking();
      stopListening();
      cancelGPSDisplay();
      break;
    case State.INSPECTING:
      break;
    case State.REPORT:
      stopSpeaking();
      break;
  }
}

function resetSession() {
  sessionId = crypto.randomUUID().slice(0, 8);
  sessionStartTime = null;
  pausedFrameDataUrl = null;
  awaitingResponse = false;
}

// ── GPS overlay ──

function showGPSOverlay() {
  document.getElementById('gps-overlay')?.classList.remove('hidden');
}

function hideGPSOverlay() {
  document.getElementById('gps-overlay')?.classList.add('hidden');
}

// ═══════════════════════════════════════════
// Enter: ANALYZING
// ═══════════════════════════════════════════

async function enterAnalyzing() {
  unlockAudio();  // unlock TTS on mobile (requires user gesture context)

  const container = document.getElementById('screen-analyzing');
  container.innerHTML = await loadScreen('active-analysis');
  showScreen('screen-analyzing');

  if (!sessionStartTime) sessionStartTime = Date.now();

  try {
    await startCamera(document.getElementById('camera-feed'));
  } catch (err) {
    console.error('[Camera] Failed:', err);
    showSubtitle('Camera access denied. Please allow camera permissions.');
    return;
  }

  connectWebSocket(handleWSMessage, handleWSDisconnect, handleWSReconnect);

  // Wait briefly for first GPS fix before starting frame loop
  await waitForGPS(3000);
  startFrameLoop();
  startGPSDisplay();

  // Button handlers
  document.getElementById('btn-inspect')?.addEventListener('click', () => {
    transitionTo(State.INSPECTING);
  });

  document.getElementById('btn-stop')?.addEventListener('click', () => {
    sendMessage({ type: 'end' });
  });

  document.getElementById('btn-close-analysis')?.addEventListener('click', () => {
    stopCamera();
    disconnectWebSocket();
    transitionTo(State.IDLE);
  });

  // Voice button — toggles conversational mic
  let voiceActive = false;
  document.getElementById('btn-voice')?.addEventListener('click', () => {
    const btn = document.getElementById('btn-voice');
    const icon = btn?.querySelector('.material-symbols-outlined');
    const label = btn?.querySelector('.font-label');

    if (!voiceActive) {
      // Start listening — user can talk to the agent
      pauseFrames();  // stop sending frames while user talks
      const started = startListening(
        // onResult: user finished a phrase
        (transcript) => {
          showSubtitle(`You: "${transcript}"`);
          sendMessage({ type: 'chat', text: transcript });
          awaitingResponse = true;
          setLoading(true);
        },
        // onStart: user began speaking — interrupt TTS
        () => {
          stopSpeaking();
          hideSubtitle();
        }
      );
      if (started) {
        voiceActive = true;
        if (icon) icon.textContent = 'mic';
        if (label) label.textContent = 'TALKING';
        btn?.classList.remove('text-white/40');
        btn?.classList.add('text-primary');
      }
    } else {
      // Stop listening and resume frame sending
      stopListening();
      resumeFrames();
      voiceActive = false;
      if (icon) icon.textContent = 'mic_off';
      if (label) label.textContent = 'VOICE';
      btn?.classList.remove('text-primary');
      btn?.classList.add('text-white/40');
    }
  });

  // Camera button disabled (facing-mode toggle not widely supported)
  // document.getElementById('btn-cam')?.addEventListener('click', () => {
  //   const icon = document.querySelector('#btn-cam .material-symbols-outlined');
  //   if (icon) icon.classList.toggle('filled');
  // });
}

function waitForGPS(timeoutMs) {
  return new Promise(resolve => {
    const start = Date.now();
    const check = () => {
      if (getGPS() || Date.now() - start > timeoutMs) {
        resolve();
        return;
      }
      setTimeout(check, 200);
    };
    check();
  });
}

function startGPSDisplay() {
  const el = document.getElementById('gps-coords');
  if (!el) return;
  let lastUpdate = 0;
  const update = (ts) => {
    if (currentState !== State.ANALYZING) return;
    // Throttle to ~2fps
    if (ts - lastUpdate > 500) {
      const gps = getGPS();
      if (gps) {
        const lat = gps.lat.toFixed(5);
        const lng = Math.abs(gps.lng).toFixed(5);
        const ns = gps.lat >= 0 ? 'N' : 'S';
        const ew = gps.lng >= 0 ? 'E' : 'W';
        el.textContent = `${lat}° ${ns}, ${lng}° ${ew}`;
      }
      lastUpdate = ts;
    }
    gpsDisplayRAF = requestAnimationFrame(update);
  };
  gpsDisplayRAF = requestAnimationFrame(update);
}

function cancelGPSDisplay() {
  if (gpsDisplayRAF) {
    cancelAnimationFrame(gpsDisplayRAF);
    gpsDisplayRAF = null;
  }
}

// ═══════════════════════════════════════════
// Enter: INSPECTING
// ═══════════════════════════════════════════

async function enterInspecting() {
  pausedFrameDataUrl = captureFrame(true);
  stopFrameLoop();
  stopSpeaking();
  clearARLabels();
  hideSubtitle();

  sendMessage({ type: 'pause' });

  const container = document.getElementById('screen-inspecting');
  container.innerHTML = await loadScreen('layer-inspector');
  showScreen('screen-inspecting');

  // Set paused frame background
  const pausedImg = document.getElementById('paused-frame');
  if (pausedImg && pausedFrameDataUrl) {
    pausedImg.src = pausedFrameDataUrl;
  }

  // Set coordinates
  const gps = getGPS();
  if (gps) {
    const coordsEl = document.getElementById('inspector-coords');
    if (coordsEl) {
      const ns = gps.lat >= 0 ? 'N' : 'S';
      const ew = gps.lng >= 0 ? 'E' : 'W';
      coordsEl.textContent = `GEO: ${gps.lat.toFixed(5)}° ${ns}, ${Math.abs(gps.lng).toFixed(5)}° ${ew}`;
    }
  }

  // Button handlers
  document.getElementById('btn-resume')?.addEventListener('click', () => {
    transitionTo(State.ANALYZING);
  });

  document.getElementById('btn-feed')?.addEventListener('click', () => {
    transitionTo(State.ANALYZING);
  });

  document.getElementById('btn-exit')?.addEventListener('click', () => {
    stopCamera();
    disconnectWebSocket();
    transitionTo(State.IDLE);
  });

  document.getElementById('btn-audio-inspector')?.addEventListener('click', () => {
    const muted = toggleMute();
    const icon = document.querySelector('#btn-audio-inspector .material-symbols-outlined');
    if (icon) icon.textContent = muted ? 'volume_off' : 'mic';
  });
}

function populateLayerInspector(data) {
  if (currentState !== State.INSPECTING) return;

  // Zoning
  if (data.zoning) {
    setText('zoning-district', data.zoning.district);
    setText('zoning-far', data.zoning.far);
    setText('zoning-description', data.zoning.description);
  }

  // Environment
  if (data.environment) {
    const pct = data.environment.canopy_pct;
    setText('env-canopy-pct', pct != null ? `${pct}%` : null);
    const bar = document.getElementById('env-canopy-bar');
    if (bar && pct != null) bar.style.width = `${Math.min(pct, 100)}%`;

    setText('env-aqi', data.environment.aqi);

    const aqiCat = document.getElementById('env-aqi-cat');
    if (aqiCat && data.environment.aqi_category) {
      aqiCat.textContent = data.environment.aqi_category;
      // Color-code based on AQI category
      const cat = data.environment.aqi_category.toLowerCase();
      if (cat === 'good') {
        aqiCat.className = 'font-label text-[9px] px-2 py-0.5 rounded-full bg-green-500/15 text-green-400';
      } else if (cat === 'moderate') {
        aqiCat.className = 'font-label text-[9px] px-2 py-0.5 rounded-full bg-yellow-500/15 text-yellow-400';
      } else {
        aqiCat.className = 'font-label text-[9px] px-2 py-0.5 rounded-full bg-error/15 text-error';
      }
    }
  }

  // Safety
  if (data.safety) {
    const floodEl = document.getElementById('safety-flood');
    if (floodEl) {
      floodEl.textContent = data.safety.flood_risk || '—';
      if (data.safety.flood_risk === 'High Risk') {
        floodEl.classList.add('text-error');
      }
    }
    setText('safety-response', data.safety.emergency_response_min != null
      ? `${data.safety.emergency_response_min} min` : null);
  }

  // 311 Complaints
  if (data.activity_311?.complaints) {
    const list = document.getElementById('complaints-list');
    if (!list) return;

    if (data.activity_311.complaints.length === 0) {
      list.innerHTML = `
        <p class="font-body text-xs text-on-surface-variant/50 italic">No recent complaints in this area.</p>
      `;
      return;
    }

    list.innerHTML = data.activity_311.complaints.map(c => `
      <div class="flex gap-3">
        <div class="w-1 min-h-[32px] rounded-full bg-primary/40 flex-shrink-0"></div>
        <div class="min-w-0">
          <span class="font-label text-[10px] text-primary/70 uppercase block">${escapeHTML(c.type)}</span>
          <p class="font-body text-xs text-on-surface-variant mt-0.5 leading-relaxed">${escapeHTML(c.description)}</p>
        </div>
      </div>
    `).join('');
  }
}

// ═══════════════════════════════════════════
// Enter: REPORT
// ═══════════════════════════════════════════

async function enterReport(payload) {
  stopCamera();
  disconnectWebSocket();

  const container = document.getElementById('screen-report');
  container.innerHTML = await loadScreen('synthesis-report');
  showScreen('screen-report');

  if (payload) populateReport(payload);

  // Button handlers
  document.getElementById('btn-export-pdf')?.addEventListener('click', () => {
    if (sessionId) {
      window.location.href = `/report/${sessionId}/pdf`;
    }
  });

  document.getElementById('btn-discard')?.addEventListener('click', () => {
    transitionTo(State.IDLE);
  });

  document.getElementById('btn-listen')?.addEventListener('click', () => {
    // Read the verdict aloud
    const verdict = document.getElementById('verdict-text');
    if (verdict) speakNarration(verdict.textContent);
  });
}

function populateReport(data) {
  setText('report-id', data.report_id);
  setText('report-location', data.location?.address);
  setText('report-date', data.date);
  setText('report-duration', data.duration || getSessionDuration());

  // Narrative timeline
  const timeline = document.getElementById('narrative-timeline');
  if (timeline && data.narrative_log?.length) {
    // Remove empty state and rebuild
    const emptyMsg = document.getElementById('timeline-empty');
    if (emptyMsg) emptyMsg.remove();
    const timelineLine = timeline.querySelector('.absolute');
    timeline.innerHTML = '';
    if (timelineLine) timeline.appendChild(timelineLine);

    data.narrative_log.forEach((entry, i) => {
      const isLast = i === data.narrative_log.length - 1;
      const node = document.createElement('div');
      node.className = 'relative pb-6';
      if (isLast) node.classList.add('pb-0');
      node.innerHTML = `
        <div class="absolute left-[-21px] top-1.5 w-[10px] h-[10px] rounded-full border-2 ${
          isLast ? 'border-primary bg-primary/20' : 'border-outline-variant/40 bg-background'
        }"></div>
        <span class="font-label text-[10px] text-primary/70 block">${escapeHTML(entry.timestamp)}</span>
        <p class="font-body text-sm text-on-surface mt-1 leading-relaxed">${highlightTerms(escapeHTML(entry.text))}</p>
      `;
      // Stagger entry appearance
      node.style.opacity = '0';
      node.style.transform = 'translateY(8px)';
      node.style.transition = 'opacity 400ms ease, transform 400ms ease';
      timeline.appendChild(node);

      setTimeout(() => {
        node.style.opacity = '1';
        node.style.transform = 'translateY(0)';
      }, 80 * i);
    });
  }

  // Captured stills
  const scroll = document.getElementById('stills-scroll');
  if (scroll && data.captured_stills?.length) {
    const stillsEmpty = document.getElementById('stills-empty');
    if (stillsEmpty) stillsEmpty.remove();
    scroll.innerHTML = data.captured_stills.map(still => `
      <div class="min-w-[280px] bg-surface-container rounded-lg overflow-hidden flex-shrink-0">
        <div class="relative h-48">
          <img src="data:image/jpeg;base64,${still.image_b64}" alt="Captured still"
            class="w-full h-full object-cover" loading="lazy">
          <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent"></div>
          <div class="absolute bottom-3 left-3 flex flex-wrap gap-1.5">
            ${(still.tags || []).map(tag => `
              <span class="font-label text-[8px] px-2 py-0.5 rounded-full border
                ${tag === 'SAFETY' ? 'bg-error/20 border-error/30 text-error' : 'bg-primary/20 border-primary/30 text-primary'}">
                ${escapeHTML(tag)}
              </span>
            `).join('')}
          </div>
        </div>
        <div class="p-3">
          <span class="font-label text-[10px] text-on-surface-variant/50">${escapeHTML(still.timestamp)}</span>
        </div>
      </div>
    `).join('');
  }

  // Verdict
  const verdict = document.getElementById('verdict-text');
  if (verdict && data.verdict) {
    verdict.innerHTML = `
      <span class="text-primary font-bold text-lg">${data.verdict.score}/10</span>
      <span class="mx-2 text-outline-variant">—</span>
      ${escapeHTML(data.verdict.summary)}
    `;
  }
}

/** Highlight data-sourced terms in narration text (zoning codes, numbers, etc.) */
function highlightTerms(text) {
  return text
    .replace(/\b(R\d[\w-]*|C\d[\w-]*|M\d[\w-]*)\b/g, '<span class="text-primary font-medium">$1</span>')
    .replace(/\b(FAR\s*[\d.]+|AQI\s*[\d]+)\b/gi, '<span class="text-primary font-medium">$1</span>')
    .replace(/\b(\d+%)\b/g, '<span class="text-primary font-medium">$1</span>');
}

// ── Utilities ──

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? '—';
}

function escapeHTML(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── GPS permission flow ──

async function requestPermissions() {
  const startBtn = document.getElementById('btn-start');
  if (startBtn) {
    startBtn.disabled = true;
    startBtn.style.opacity = '0.6';
  }

  try {
    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 10000,
      });
    });
    seedGPS(position);
    hideGPSOverlay();
    transitionTo(State.ANALYZING);
  } catch {
    showGPSOverlay();
  } finally {
    if (startBtn) {
      startBtn.disabled = false;
      startBtn.style.opacity = '1';
    }
  }
}

// ── Init ──

function init() {
  document.getElementById('btn-start')?.addEventListener('click', requestPermissions);
  document.getElementById('btn-retry-gps')?.addEventListener('click', requestPermissions);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
