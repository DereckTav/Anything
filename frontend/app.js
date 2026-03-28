import {
  startCamera, stopCamera, captureFrame, getGPS, seedGPS,
  connectWebSocket, disconnectWebSocket, sendMessage, isConnected,
} from './camera.js';
import {
  speakNarration, stopSpeaking, toggleMute, isMuted, unlockAudio,
  startVoice, stopVoice, isVoiceConnected, sendVoiceFrame,
} from './audio.js';
import { renderARLabels, clearARLabels, showSubtitle, hideSubtitle } from './overlay.js';

// ── State machine ──────────────────────────────────────────────

const State = Object.freeze({
  IDLE:       'IDLE',
  EXPLORING:  'EXPLORING',
  NEARBY:     'NEARBY',
  DETAIL:     'DETAIL',
});

let currentState     = State.IDLE;
let voiceActive      = false;
let voiceFrameInterval = null;
let gpsDisplayRAF    = null;
let discoveryTimer   = null;
let currentPOIs      = [];   // last received poi_chips
let selectedPOI      = null; // POI tapped in nearby list or chips

// ── Screen loading ─────────────────────────────────────────────

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
  void target.offsetHeight;
  requestAnimationFrame(() => { target.style.opacity = '1'; });
}

// ── WebSocket message handler ──────────────────────────────────

function handleWSMessage(data) {
  switch (data.type) {
    case 'narration':
      if (currentState === State.EXPLORING && !voiceActive) {
        speakNarration(data.text);
        showSubtitle(data.text);
      }
      break;

    case 'poi_chips':
      if (data.pois?.length) {
        currentPOIs = data.pois;
        if (currentState === State.EXPLORING) renderPOIChips(data.pois);
      }
      break;

    case 'gps_required':
      showGPSOverlay();
      break;

    case 'error':
      console.error('[WS] Backend error:', data.message);
      break;
  }
}

// ── POI chip rendering ─────────────────────────────────────────

function renderPOIChips(pois) {
  const container = document.getElementById('poi-chips-container');
  if (!container) return;

  container.innerHTML = '';
  pois.slice(0, 5).forEach(poi => {
    const chip = document.createElement('button');
    chip.className = [
      'flex-shrink-0 glass-panel rounded-full px-4 py-2',
      'border border-primary/20 hover:border-primary/60 transition-all duration-200',
      'flex items-center gap-2 max-w-[220px]',
      'active:scale-95',
    ].join(' ');

    const walkText = poi.walk_min != null ? `${poi.walk_min} min` : '';

    chip.innerHTML = `
      <span class="material-symbols-outlined text-sm text-primary/70">place</span>
      <span class="font-body text-xs text-white truncate">${escapeHTML(poi.name)}</span>
      ${walkText ? `<span class="font-label text-[9px] text-primary/50 flex-shrink-0">${escapeHTML(walkText)}</span>` : ''}
    `;

    chip.addEventListener('click', () => openPlaceDetail(poi));
    container.appendChild(chip);
  });
}

function clearPOIChips() {
  const container = document.getElementById('poi-chips-container');
  if (container) container.innerHTML = '';
}

// ── Proactive discovery loop ───────────────────────────────────

function startDiscoveryLoop() {
  stopDiscoveryLoop();
  // Fire once immediately, then every 60s
  triggerDiscovery();
  discoveryTimer = setInterval(triggerDiscovery, 60_000);
}

function stopDiscoveryLoop() {
  if (discoveryTimer) {
    clearInterval(discoveryTimer);
    discoveryTimer = null;
  }
}

function triggerDiscovery() {
  const gps = getGPS();
  if (!gps || currentState !== State.EXPLORING) return;
  sendMessage({ type: 'discover', gps: { lat: gps.lat, lng: gps.lng } });
}

// ── State transitions ──────────────────────────────────────────

async function transitionTo(newState, payload = null) {
  await cleanup(currentState);
  currentState = newState;

  switch (newState) {
    case State.IDLE:       showScreen('screen-idle'); resetSession(); break;
    case State.EXPLORING:  await enterExploring(); break;
    case State.NEARBY:     await enterNearby(); break;
    case State.DETAIL:     await enterDetail(payload); break;
  }
}

async function cleanup(state) {
  switch (state) {
    case State.EXPLORING:
      stopDiscoveryLoop();
      stopVoiceMode();
      clearARLabels();
      hideSubtitle();
      stopSpeaking();
      cancelGPSDisplay();
      break;
    case State.NEARBY:
    case State.DETAIL:
      break;
  }
}

function resetSession() {
  currentPOIs  = [];
  selectedPOI  = null;
  voiceActive  = false;
}

// ── GPS overlay ────────────────────────────────────────────────

function showGPSOverlay() {
  document.getElementById('gps-overlay')?.classList.remove('hidden');
}
function hideGPSOverlay() {
  document.getElementById('gps-overlay')?.classList.add('hidden');
}

// ═══════════════════════════════════════════════════════════════
// Enter: EXPLORING
// ═══════════════════════════════════════════════════════════════

async function enterExploring() {
  unlockAudio();

  const container = document.getElementById('screen-exploring');
  container.innerHTML = await loadScreen('explore');
  showScreen('screen-exploring');

  try {
    await startCamera(document.getElementById('camera-feed'));
  } catch (err) {
    console.error('[Camera]', err);
    showSubtitle('Camera access denied — voice guide still works.');
  }

  connectWebSocket(handleWSMessage, () => {}, () => {});
  await waitForGPS(3000);
  startGPSDisplay();
  startDiscoveryLoop();

  // Voice button
  document.getElementById('btn-voice')?.addEventListener('click', toggleVoiceMode);

  // Nearby button
  document.getElementById('btn-nearby')?.addEventListener('click', () => {
    transitionTo(State.NEARBY);
  });

  // Exit button
  document.getElementById('btn-close-analysis')?.addEventListener('click', () => {
    stopCamera();
    disconnectWebSocket();
    transitionTo(State.IDLE);
  });
<<<<<<< HEAD
=======

  // Voice button — toggles real-time voice conversation via Gemini Live
  function deactivateVoice() {
    stopVoice();
    resumeFrames();
    voiceActive = false;
    if (voiceFrameInterval) { clearInterval(voiceFrameInterval); voiceFrameInterval = null; }
    const btn = document.getElementById('btn-voice');
    const icon = btn?.querySelector('.material-symbols-outlined');
    const label = btn?.querySelector('.font-label');
    if (icon) icon.textContent = 'mic_off';
    if (label) label.textContent = 'VOICE';
    btn?.classList.remove('text-primary');
    btn?.classList.add('text-white/40');
    hideSubtitle();
  }

  document.getElementById('btn-voice')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-voice');
    const icon = btn?.querySelector('.material-symbols-outlined');
    const label = btn?.querySelector('.font-label');

    if (!voiceActive) {
      pauseFrames();  // stop sending frames while in voice mode
      stopSpeaking(); // stop any TTS

      const gps = getGPS();
      let agentBuf = '';
      const started = await startVoice(
        (msg) => {
          if (msg.role === 'agent') {
            agentBuf += msg.text;
            const display = agentBuf.length > 120 ? '...' + agentBuf.slice(-120) : agentBuf;
            showSubtitle(display);
          } else if (msg.role === 'user') {
            // Local recognition sends full interim text
            showSubtitle(msg.text);
          }
        },
        (status) => {
          if (status === 'listening' && voiceActive) {
            if (label) label.textContent = 'LISTENING';
            agentBuf = '';
          } else if (status === 'speaking' && voiceActive) {
            if (label) label.textContent = 'SPEAKING';
          }
        },
        gps,
        () => {
          // Silence timeout — auto-stop voice and have AI narrate the current view
          console.log('[App] Silence timeout — ending voice mode');
          deactivateVoice();
          // Trigger a normal AI analysis so the AI speaks about the current view
          const frame = captureFrame();
          if (frame) {
            speakNarration('Let me tell you about what I see.');
            sendMessage(frame, sessionId);
          }
        }
      );

      if (started) {
        voiceActive = true;
        if (icon) icon.textContent = 'mic';
        if (label) label.textContent = 'LISTENING';
        btn?.classList.remove('text-white/40');
        btn?.classList.add('text-primary');

        // Send a frame for visual context every 5 seconds
        voiceFrameInterval = setInterval(() => {
          const frame = captureFrame();
          if (frame) sendVoiceFrame(frame);
        }, 5000);
        // Send first frame immediately
        const firstFrame = captureFrame();
        if (firstFrame) sendVoiceFrame(firstFrame);
      }
    } else {
      deactivateVoice();
    }
  });

  // Camera button disabled (facing-mode toggle not widely supported)
  // document.getElementById('btn-cam')?.addEventListener('click', () => {
  //   const icon = document.querySelector('#btn-cam .material-symbols-outlined');
  //   if (icon) icon.classList.toggle('filled');
  // });
>>>>>>> refs/remotes/origin/main
}

// ── Voice mode ────────────────────────────────────────────────

async function toggleVoiceMode() {
  const btn   = document.getElementById('btn-voice');
  const icon  = btn?.querySelector('.material-symbols-outlined');
  const label = btn?.querySelector('.font-label');
  const statusBar   = document.getElementById('voice-status-bar');
  const statusLabel = document.getElementById('voice-status-label');

  if (!voiceActive) {
    stopSpeaking();
    const gps = getGPS();

    const started = await startVoice(
      (msg) => {
        // Show rolling transcript as subtitle
        if (msg.role === 'agent' || msg.role === 'user') {
          const text = msg.text || '';
          const display = text.length > 120 ? '...' + text.slice(-120) : text;
          showSubtitle(display);
        }
      },
      (status) => {
        if (!voiceActive) return;
        const labels = { listening: 'Listening', speaking: 'Speaking', idle: 'Voice' };
        if (statusLabel) statusLabel.textContent = labels[status] || 'Voice';
        if (status === 'listening' || status === 'idle') {
          if (label) label.textContent = status === 'listening' ? 'LISTENING' : 'VOICE';
        } else if (status === 'speaking') {
          if (label) label.textContent = 'SPEAKING';
        }
      },
      gps
    );

    if (started) {
      voiceActive = true;
      if (icon)  icon.textContent = 'mic';
      if (label) label.textContent = 'LISTENING';
      btn?.classList.remove('text-white/60');
      btn?.classList.add('text-primary', 'scale-110');
      statusBar?.classList.remove('hidden');

      // Send camera frame for visual context every 8s
      voiceFrameInterval = setInterval(() => {
        const frame = captureFrame();
        if (frame) sendVoiceFrame(frame);
      }, 8000);
      const firstFrame = captureFrame();
      if (firstFrame) sendVoiceFrame(firstFrame);
    }

  } else {
    stopVoiceMode();
    if (icon)  icon.textContent = 'mic';
    if (label) label.textContent = 'VOICE';
    btn?.classList.remove('text-primary', 'scale-110');
    btn?.classList.add('text-white/60');
    hideSubtitle();
  }
}

function stopVoiceMode() {
  if (!voiceActive) return;
  voiceActive = false;
  stopVoice();
  if (voiceFrameInterval) {
    clearInterval(voiceFrameInterval);
    voiceFrameInterval = null;
  }
  document.getElementById('voice-status-bar')?.classList.add('hidden');
}

// ── GPS display ────────────────────────────────────────────────

function waitForGPS(timeoutMs) {
  return new Promise(resolve => {
    const start = Date.now();
    const check = () => {
      if (getGPS() || Date.now() - start > timeoutMs) { resolve(); return; }
      setTimeout(check, 200);
    };
    check();
  });
}

function startGPSDisplay() {
  const el = document.getElementById('gps-coords');
  if (!el) return;
  let lastTs = 0;
  const update = (ts) => {
    if (currentState !== State.EXPLORING) return;
    if (ts - lastTs > 500) {
      const gps = getGPS();
      if (gps) {
        const ns = gps.lat >= 0 ? 'N' : 'S';
        const ew = gps.lng >= 0 ? 'E' : 'W';
        el.textContent = `${gps.lat.toFixed(4)}°${ns} ${Math.abs(gps.lng).toFixed(4)}°${ew}`;
      }
      lastTs = ts;
    }
    gpsDisplayRAF = requestAnimationFrame(update);
  };
  gpsDisplayRAF = requestAnimationFrame(update);
}

function cancelGPSDisplay() {
  if (gpsDisplayRAF) { cancelAnimationFrame(gpsDisplayRAF); gpsDisplayRAF = null; }
}

// ═══════════════════════════════════════════════════════════════
// Enter: NEARBY
// ═══════════════════════════════════════════════════════════════

async function enterNearby() {
  const container = document.getElementById('screen-nearby');
  container.innerHTML = await loadScreen('nearby');
  showScreen('screen-nearby');

  document.getElementById('btn-back-nearby')?.addEventListener('click', () => {
    transitionTo(State.EXPLORING);
  });

  const listEl     = document.getElementById('nearby-list');
  const loadingEl  = document.getElementById('nearby-loading');
  const emptyEl    = document.getElementById('nearby-empty');

  if (!currentPOIs.length) {
    loadingEl?.classList.add('hidden');
    emptyEl?.classList.remove('hidden');
    return;
  }

  loadingEl?.classList.add('hidden');
  listEl?.classList.remove('hidden');

  currentPOIs.forEach(poi => {
    const item = document.createElement('button');
    item.className = [
      'w-full glass-panel rounded-xl p-4 border border-outline-variant/30',
      'hover:border-primary/30 transition-all duration-200 text-left active:scale-[0.98]',
    ].join(' ');

    const walkText = poi.walk_min != null ? `${poi.walk_min} min walk` : '';

    item.innerHTML = `
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <span class="font-label text-[8px] uppercase tracking-wider text-primary/60 block mb-0.5">
            ${escapeHTML(poi.type || 'Place')}
          </span>
          <h3 class="font-headline italic text-lg text-primary leading-tight truncate">
            ${escapeHTML(poi.name)}
          </h3>
          ${poi.address ? `<p class="font-label text-[10px] text-on-surface-variant/50 mt-1 truncate">${escapeHTML(poi.address)}</p>` : ''}
        </div>
        <div class="flex flex-col items-end gap-1 flex-shrink-0">
          ${walkText ? `
          <div class="flex items-center gap-1 text-primary/70">
            <span class="material-symbols-outlined text-sm">directions_walk</span>
            <span class="font-label text-[10px]">${escapeHTML(walkText)}</span>
          </div>` : ''}
          <span class="material-symbols-outlined text-sm text-white/20">chevron_right</span>
        </div>
      </div>
    `;

    item.addEventListener('click', () => openPlaceDetail(poi));
    listEl?.appendChild(item);
  });
}

// ═══════════════════════════════════════════════════════════════
// Open: DETAIL
// ═══════════════════════════════════════════════════════════════

function openPlaceDetail(poi) {
  selectedPOI = poi;
  transitionTo(State.DETAIL, poi);
}

async function enterDetail(poi) {
  const container = document.getElementById('screen-detail');
  container.innerHTML = await loadScreen('place-detail');
  showScreen('screen-detail');

  if (!poi) return;

  // Populate fields
  setText('detail-name',    poi.name);
  setText('detail-type',    poi.type || 'Point of Interest');
  setText('detail-address', poi.address || '—');

  if (poi.walk_min != null) {
    const walkText = poi.walk_min < 1 ? 'under 1 min walk' : `${poi.walk_min} min walk`;
    setText('detail-walk-time', walkText);
  }

  if (poi.lat != null && poi.lng != null) {
    const ns = poi.lat >= 0 ? 'N' : 'S';
    const ew = poi.lng >= 0 ? 'E' : 'W';
    setText('detail-coords', `${Math.abs(poi.lat).toFixed(5)}°${ns}, ${Math.abs(poi.lng).toFixed(5)}°${ew}`);
  }

  // Maps link
  const mapsBtn = document.getElementById('btn-take-me-there');
  if (mapsBtn) {
    if (poi.maps_url) {
      mapsBtn.href = poi.maps_url;
    } else if (poi.lat != null && poi.lng != null) {
      const encoded = encodeURIComponent(poi.name);
      mapsBtn.href = `https://www.google.com/maps/dir/?api=1&destination=${poi.lat},${poi.lng}&travelmode=walking&destination_place=${encoded}`;
    }
  }

  // Back button — go back to wherever we came from
  document.getElementById('btn-back-detail')?.addEventListener('click', () => {
    // If NEARBY had POIs loaded, return there; otherwise go to EXPLORING
    if (currentPOIs.length > 0) {
      transitionTo(State.NEARBY);
    } else {
      transitionTo(State.EXPLORING);
    }
  });
}

// ── Utilities ──────────────────────────────────────────────────

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

// ── GPS permission flow ────────────────────────────────────────

async function requestPermissions() {
  const startBtn = document.getElementById('btn-start');
  if (startBtn) { startBtn.disabled = true; startBtn.style.opacity = '0.6'; }

  try {
    const position = await new Promise((resolve, reject) =>
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true, timeout: 10000,
      })
    );
    seedGPS(position);
    hideGPSOverlay();
    transitionTo(State.EXPLORING);
  } catch {
    showGPSOverlay();
  } finally {
    if (startBtn) { startBtn.disabled = false; startBtn.style.opacity = '1'; }
  }
}

// ── Init ───────────────────────────────────────────────────────

function init() {
  document.getElementById('btn-start')?.addEventListener('click', requestPermissions);
  document.getElementById('btn-retry-gps')?.addEventListener('click', requestPermissions);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
