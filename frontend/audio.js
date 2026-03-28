const queue = [];
let speaking = false;
let muted = false;
let cachedVoice = null;
let voicesLoaded = false;

// ── Speech Recognition (STT) ──
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let listening = false;
let onSpeechResultCb = null;
let onSpeechStartCb = null;
let shouldContinueListening = false;

// Preload voices — Chrome loads them asynchronously
if ('speechSynthesis' in window) {
  const loadVoices = () => {
    const voices = speechSynthesis.getVoices();
    if (voices.length === 0) return;
    voicesLoaded = true;
    cachedVoice = voices.find(v =>
      v.lang.startsWith('en') && /samantha|google|natural|daniel|karen/i.test(v.name)
    ) || voices.find(v => v.lang.startsWith('en') && v.localService) || null;
  };

  loadVoices();
  speechSynthesis.addEventListener('voiceschanged', loadVoices);
}

// ═══════════════════════════════════════════
// TTS (Text-to-Speech)
// ═══════════════════════════════════════════

// Mobile browsers block TTS until a user gesture triggers it once.
// Call this on the first user tap to unlock audio.
let audioUnlocked = false;
export function unlockAudio() {
  if (audioUnlocked || !('speechSynthesis' in window)) return;
  // Speak an empty utterance to unlock
  const unlock = new SpeechSynthesisUtterance('');
  unlock.volume = 0;
  speechSynthesis.speak(unlock);
  audioUnlocked = true;
  console.log('[TTS] Audio unlocked');
}

export function speakNarration(text) {
  if (!text || !('speechSynthesis' in window)) return;
  if (muted) return;

  queue.push(text);
  processQueue();
}

function processQueue() {
  if (speaking || muted || queue.length === 0) return;

  speaking = true;
  const text = queue.shift();
  const utterance = new SpeechSynthesisUtterance(text);

  utterance.rate = 0.95;
  utterance.pitch = 1.0;
  utterance.volume = 1.0;

  if (cachedVoice) {
    utterance.voice = cachedVoice;
  }

  utterance.onend = () => {
    speaking = false;
    processQueue();
  };

  utterance.onerror = (e) => {
    // 'interrupted' and 'canceled' are expected when calling cancel()
    if (e.error !== 'interrupted' && e.error !== 'canceled') {
      console.warn('[TTS] Error:', e.error);
    }
    speaking = false;
    processQueue();
  };

  speechSynthesis.speak(utterance);
}

export function stopSpeaking() {
  queue.length = 0;
  speaking = false;
  if ('speechSynthesis' in window) {
    speechSynthesis.cancel();
  }
}

export function isSpeaking() {
  return speaking;
}

// ═══════════════════════════════════════════
// STT (Speech-to-Text) — conversational input
// ═══════════════════════════════════════════

/**
 * Start continuous listening. Calls onResult(transcript) when user finishes a phrase.
 * Calls onStart() when user begins speaking (use this to interrupt TTS).
 */
export function startListening(onResult, onStart) {
  if (!SpeechRecognition) {
    console.warn('[STT] SpeechRecognition not supported');
    return false;
  }

  onSpeechResultCb = onResult;
  onSpeechStartCb = onStart;
  shouldContinueListening = true;

  if (recognition) {
    recognition.abort();
    recognition = null;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.continuous = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    listening = true;
    console.log('[STT] Listening...');
  };

  recognition.onspeechstart = () => {
    // User started talking — interrupt TTS
    if (onSpeechStartCb) onSpeechStartCb();
  };

  recognition.onresult = (event) => {
    // Get the latest final result
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        const transcript = event.results[i][0].transcript.trim();
        if (transcript && onSpeechResultCb) {
          console.log('[STT] Result:', transcript);
          onSpeechResultCb(transcript);
        }
      }
    }
  };

  recognition.onerror = (e) => {
    if (e.error === 'aborted' || e.error === 'no-speech') return;
    console.warn('[STT] Error:', e.error);
  };

  recognition.onend = () => {
    listening = false;
    // Auto-restart if we should still be listening
    if (shouldContinueListening) {
      try {
        recognition.start();
      } catch {
        // Already started or other issue — ignore
      }
    }
  };

  try {
    recognition.start();
    return true;
  } catch {
    return false;
  }
}

export function stopListening() {
  shouldContinueListening = false;
  listening = false;
  if (recognition) {
    recognition.abort();
    recognition = null;
  }
}

export function isListening() {
  return listening;
}

/** Toggle mute state. Returns new muted value. */
export function toggleMute() {
  muted = !muted;
  if (muted) stopSpeaking();
  return muted;
}

export function isMuted() {
  return muted;
}
