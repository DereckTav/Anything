let videoStream = null;
let videoEl = null;
let canvas = null;
let ctx = null;
let gpsPosition = null;
let gpsWatchId = null;

let ws = null;
let onMessageCb = null;
let onDisconnectCb = null;
let onReconnectCb = null;
let wsUrl = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_DELAY = 16000;
let messageQueue = [];

// ═══════════════════════════════════════════
// Camera
// ═══════════════════════════════════════════

export async function startCamera(videoElement) {
  videoEl = videoElement;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: 'environment',
        width: { ideal: 640 },
        height: { ideal: 480 },
      },
      audio: false,
    });

    videoStream = stream;
    videoEl.srcObject = stream;
    await videoEl.play();

    canvas = document.createElement('canvas');
    ctx = canvas.getContext('2d');

    startGPSWatch();
  } catch (err) {
    videoStream = null;
    throw err;
  }
}

export function stopCamera() {
  if (videoStream) {
    videoStream.getTracks().forEach(t => t.stop());
    videoStream = null;
  }
  if (videoEl) {
    videoEl.srcObject = null;
    videoEl = null;
  }
  canvas = null;
  ctx = null;
  stopGPSWatch();
}

/**
 * Capture the current video frame as a base64 JPEG string.
 * @param {boolean} withPrefix If true, returns the full data:image URL for <img> src. Otherwise returns raw base64.
 * @returns {string|null}
 */
export function captureFrame(withPrefix = false) {
  if (!videoEl || !canvas || !ctx) return null;
  if (!videoEl.videoWidth) return null;

  canvas.width = videoEl.videoWidth;
  canvas.height = videoEl.videoHeight;
  ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

  const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
  return withPrefix ? dataUrl : dataUrl.replace(/^data:image\/jpeg;base64,/, '');
}

// ═══════════════════════════════════════════
// GPS
// ═══════════════════════════════════════════

function startGPSWatch() {
  if (gpsWatchId != null) return;

  gpsWatchId = navigator.geolocation.watchPosition(
    pos => {
      gpsPosition = {
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
      };
    },
    err => console.warn('[GPS] Watch error:', err.message),
    { enableHighAccuracy: true, maximumAge: 4000, timeout: 10000 }
  );
}

function stopGPSWatch() {
  if (gpsWatchId != null) {
    navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchId = null;
  }
  gpsPosition = null;
}

export function getGPS() {
  return gpsPosition;
}

export function seedGPS(position) {
  gpsPosition = {
    lat: position.coords.latitude,
    lng: position.coords.longitude,
    accuracy: position.coords.accuracy,
  };
}

// ═══════════════════════════════════════════
// WebSocket (with auto-reconnect + queue)
// ═══════════════════════════════════════════

export function connectWebSocket(onMessage, onDisconnect, onReconnect) {
  onMessageCb = onMessage;
  onDisconnectCb = onDisconnect;
  onReconnectCb = onReconnect;
  reconnectAttempts = 0;
  messageQueue = [];

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  wsUrl = `${protocol}//${location.host}/ws/analyze`;

  openSocket();
}

function openSocket() {
  if (!wsUrl) return;
  try {
    ws = new WebSocket(wsUrl);
  } catch {
    scheduleReconnect();
    return;
  }

  ws.addEventListener('open', () => {
    console.log('[WS] Connected');
    const wasReconnect = reconnectAttempts > 0;
    reconnectAttempts = 0;

    // Flush queued messages
    while (messageQueue.length > 0) {
      const msg = messageQueue.shift();
      ws.send(msg);
    }

    if (wasReconnect && onReconnectCb) onReconnectCb();
  });

  ws.addEventListener('message', evt => {
    try {
      const data = JSON.parse(evt.data);
      if (onMessageCb) onMessageCb(data);
    } catch (e) {
      console.error('[WS] Parse error:', e);
    }
  });

  ws.addEventListener('close', evt => {
    console.log('[WS] Closed:', evt.code, evt.reason);
    if (onDisconnectCb) onDisconnectCb();
    // Only reconnect on abnormal close and if we haven't intentionally disconnected
    if (wsUrl && evt.code !== 1000) {
      scheduleReconnect();
    }
  });

  ws.addEventListener('error', () => {
    // error fires before close — close handler will trigger reconnect
  });
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectAttempts++;
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), MAX_RECONNECT_DELAY);
  console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttempts})`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    openSocket();
  }, delay);
}

export function disconnectWebSocket() {
  wsUrl = null;
  messageQueue = [];
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close(1000, 'Client disconnect');
    ws = null;
  }
}

export function sendMessage(obj) {
  const json = JSON.stringify(obj);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(json);
  } else {
    // Queue for when connection reopens (only keep last 3 to avoid memory bloat)
    messageQueue.push(json);
    if (messageQueue.length > 3) messageQueue.shift();
  }
}

export function isConnected() {
  return ws != null && ws.readyState === WebSocket.OPEN;
}
