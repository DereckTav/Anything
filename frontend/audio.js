// ═══════════════════════════════════════════
// URBANLENS Audio — Real-time voice via Gemini Live API
// ═══════════════════════════════════════════

// ── State ──
let voiceWs = null;
let micStream = null;
let audioContext = null;
let micProcessor = null;
let playing = false;
let muted = false;
let voiceConnected = false;

// TTS fallback state
const ttsQueue = [];
let ttsSpeaking = false;
let cachedVoice = null;

// Silence detection
let silenceTimer = null;
let lastSpeechTime = 0;
const SILENCE_TIMEOUT_MS = 5000;  // 5 seconds of silence → auto-stop
let onSilenceTimeoutCb = null;

// Callbacks
let onTranscriptCb = null;    // called with text transcription of user/agent speech
let onVoiceStatusCb = null;   // called with status updates ('listening', 'speaking', 'idle')

// Preload TTS voices for fallback
if ('speechSynthesis' in window) {
  const loadVoices = () => {
    const voices = speechSynthesis.getVoices();
    cachedVoice = voices.find(v =>
      v.lang.startsWith('en') && /samantha|google|natural|daniel|karen/i.test(v.name)
    ) || voices.find(v => v.lang.startsWith('en') && v.localService) || null;
  };
  loadVoices();
  speechSynthesis.addEventListener('voiceschanged', loadVoices);
}

// ═══════════════════════════════════════════
// Real-time Voice (Gemini Live API via backend proxy)
// ═══════════════════════════════════════════

/**
 * Connect to the voice WebSocket and start streaming mic audio.
 * @param {Function} onTranscript - called with {role, text} for transcriptions
 * @param {Function} onStatus - called with status string
 * @param {object} gps - {lat, lng} for tool context
 * @param {Function} onSilenceTimeout - called when user is silent for 5 seconds
 */
export async function startVoice(onTranscript, onStatus, gps, onSilenceTimeout) {
  onTranscriptCb = onTranscript;
  onVoiceStatusCb = onStatus;
  onSilenceTimeoutCb = onSilenceTimeout || null;
  lastSpeechTime = Date.now();

  // Build WebSocket URL for voice endpoint
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}/ws/voice${gps ? `?lat=${gps.lat}&lng=${gps.lng}` : ''}`;

  try {
    // Get mic access
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      }
    });

    // Set up AudioContext for resampling to 16kHz PCM
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(micStream);

    // ScriptProcessor to capture raw PCM (4096 samples per chunk)
    micProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    micProcessor.onaudioprocess = (e) => {
      if (!voiceConnected || muted) return;
      const float32 = e.inputBuffer.getChannelData(0);
      // Noise gate — skip silent/quiet chunks
      let rms = 0;
      for (let i = 0; i < float32.length; i++) rms += float32[i] * float32[i];
      rms = Math.sqrt(rms / float32.length);
      if (rms < 0.005) return;
      // User is speaking — reset silence timer
      lastSpeechTime = Date.now();
      // Convert float32 [-1,1] to int16 PCM
      const int16 = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32767)));
      }
      // Send as base64
      if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
        const b64 = arrayBufferToBase64(int16.buffer);
        voiceWs.send(JSON.stringify({ type: 'audio', data: b64 }));
      }
    };
    source.connect(micProcessor);
    micProcessor.connect(audioContext.destination);

    // Connect WebSocket
    voiceWs = new WebSocket(wsUrl);
    voiceWs.binaryType = 'arraybuffer';

    voiceWs.onopen = () => {
      voiceConnected = true;
      lastSpeechTime = Date.now();
      if (onVoiceStatusCb) onVoiceStatusCb('listening');
      console.log('[Voice] Connected');

      // Start silence detection timer
      if (silenceTimer) clearInterval(silenceTimer);
      silenceTimer = setInterval(() => {
        if (!voiceConnected) return;
        const elapsed = Date.now() - lastSpeechTime;
        if (elapsed >= SILENCE_TIMEOUT_MS) {
          console.log('[Voice] Silence timeout — auto-stopping');
          if (onSilenceTimeoutCb) onSilenceTimeoutCb();
        }
      }, 1000);
    };

    voiceWs.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === 'audio') {
        // Play audio response (24kHz PCM base64)
        playPCMAudio(msg.data);
        lastSpeechTime = Date.now();  // AI speaking = conversation active
        if (onVoiceStatusCb) onVoiceStatusCb('speaking');
      } else if (msg.type === 'transcript') {
        // Text transcription of speech
        if (onTranscriptCb) onTranscriptCb(msg);
      } else if (msg.type === 'turn_complete') {
        if (onVoiceStatusCb) onVoiceStatusCb('listening');
      } else if (msg.type === 'error') {
        console.error('[Voice] Error:', msg.message);
        if (onTranscriptCb) onTranscriptCb({ role: 'system', text: msg.message });
      }
    };

    voiceWs.onclose = () => {
      voiceConnected = false;
      if (onVoiceStatusCb) onVoiceStatusCb('idle');
      console.log('[Voice] Disconnected');
    };

    voiceWs.onerror = (e) => {
      console.error('[Voice] WebSocket error:', e);
    };

    return true;
  } catch (err) {
    console.error('[Voice] Failed to start:', err);
    return false;
  }
}

export function stopVoice() {
  voiceConnected = false;

  if (silenceTimer) {
    clearInterval(silenceTimer);
    silenceTimer = null;
  }
  onSilenceTimeoutCb = null;

  if (micProcessor) {
    micProcessor.disconnect();
    micProcessor = null;
  }
  if (audioContext) {
    audioContext.close().catch(() => {});
    audioContext = null;
  }
  if (micStream) {
    micStream.getTracks().forEach(t => t.stop());
    micStream = null;
  }
  if (voiceWs) {
    voiceWs.close(1000);
    voiceWs = null;
  }
  if (onVoiceStatusCb) onVoiceStatusCb('idle');
}

export function isVoiceConnected() {
  return voiceConnected;
}

// Update GPS context for the voice session
export function updateVoiceGPS(gps) {
  if (voiceWs && voiceWs.readyState === WebSocket.OPEN && gps) {
    voiceWs.send(JSON.stringify({ type: 'gps', lat: gps.lat, lng: gps.lng }));
  }
}

// Send a camera frame to the voice session for visual context
export function sendVoiceFrame(imageB64) {
  if (voiceWs && voiceWs.readyState === WebSocket.OPEN && imageB64) {
    voiceWs.send(JSON.stringify({ type: 'frame', image_b64: imageB64 }));
  }
}

// ── PCM Audio Playback (24kHz → 48kHz upsampled) ──

let playbackCtx = null;
let nextPlayTime = 0;

function getPlaybackCtx() {
  if (!playbackCtx || playbackCtx.state === 'closed') {
    playbackCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
    nextPlayTime = 0;
  }
  return playbackCtx;
}

function playPCMAudio(base64Data) {
  const ctx = getPlaybackCtx();
  const bytes = base64ToArrayBuffer(base64Data);
  const int16 = new Int16Array(bytes);

  // Upsample 24kHz → 48kHz with linear interpolation for smoother audio
  const upsampled = new Float32Array(int16.length * 2);
  for (let i = 0; i < int16.length; i++) {
    const s = int16[i] / 32768;
    const next = i < int16.length - 1 ? int16[i + 1] / 32768 : s;
    upsampled[i * 2] = s;
    upsampled[i * 2 + 1] = (s + next) / 2;
  }

  const buffer = ctx.createBuffer(1, upsampled.length, 48000);
  buffer.getChannelData(0).set(upsampled);

  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);

  // Schedule seamlessly after the previous chunk
  const now = ctx.currentTime;
  if (nextPlayTime < now) nextPlayTime = now;
  source.start(nextPlayTime);
  nextPlayTime += buffer.duration;
}

// ── Helpers ──

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

// ═══════════════════════════════════════════
// TTS Fallback (Web Speech API)
// ═══════════════════════════════════════════

let audioUnlockDone = false;
export function unlockAudio() {
  if (audioUnlockDone || !('speechSynthesis' in window)) return;
  const u = new SpeechSynthesisUtterance('');
  u.volume = 0;
  speechSynthesis.speak(u);
  audioUnlockDone = true;
}

export function speakNarration(text) {
  if (!text || !('speechSynthesis' in window) || muted) return;
  ttsQueue.push(text);
  processTTSQueue();
}

function processTTSQueue() {
  if (ttsSpeaking || muted || ttsQueue.length === 0) return;
  ttsSpeaking = true;
  const text = ttsQueue.shift();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.95;
  utterance.pitch = 1.0;
  utterance.volume = 1.0;
  if (cachedVoice) utterance.voice = cachedVoice;
  utterance.onend = () => { ttsSpeaking = false; processTTSQueue(); };
  utterance.onerror = (e) => {
    if (e.error !== 'interrupted' && e.error !== 'canceled') console.warn('[TTS] Error:', e.error);
    ttsSpeaking = false;
    processTTSQueue();
  };
  speechSynthesis.speak(utterance);
}

export function stopSpeaking() {
  ttsQueue.length = 0;
  ttsSpeaking = false;
  if ('speechSynthesis' in window) speechSynthesis.cancel();
}

// Keep old exports for compatibility
export function startListening() { return false; }
export function stopListening() {}

export function toggleMute() {
  muted = !muted;
  if (muted) stopSpeaking();
  return muted;
}

export function isMuted() {
  return muted;
}
