const queue = [];
let speaking = false;
let muted = false;
let cachedVoice = null;
let voicesLoaded = false;

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

/** Toggle mute state. Returns new muted value. */
export function toggleMute() {
  muted = !muted;
  if (muted) stopSpeaking();
  return muted;
}

export function isMuted() {
  return muted;
}
