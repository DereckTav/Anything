const POSITION_MAP = {
  'top-left':     { top: '15%', left: '5%' },
  'top-right':    { top: '15%', left: '60%' },
  'mid-left':     { top: '45%', left: '5%' },
  'mid-right':    { top: '45%', left: '55%' },
  'bottom-left':  { top: '70%', left: '5%' },
  'bottom-right': { top: '70%', left: '55%' },
};

const STAGGER_MS = 120;

let currentLabels = [];
let exitTimer = null;

// ═══════════════════════════════════════════
// AR Labels
// ═══════════════════════════════════════════

export function renderARLabels(labels) {
  const container = document.getElementById('ar-overlay');
  if (!container) return;
  if (exitTimer) { clearTimeout(exitTimer); exitTimer = null; }

  // Fade out existing labels
  const existing = container.querySelectorAll('.ar-label');
  existing.forEach(el => {
    el.classList.remove('ar-label-enter');
    el.classList.add('ar-label-exit');
  });

  exitTimer = setTimeout(() => {
    exitTimer = null;
    container.innerHTML = '';
    currentLabels = labels || [];

    currentLabels.forEach((label, i) => {
      const pos = POSITION_MAP[label.position] || POSITION_MAP['mid-left'];

      const el = document.createElement('div');
      el.className = 'ar-label absolute';
      el.style.top = pos.top;
      el.style.left = pos.left;
      el.style.maxWidth = '45%';
      el.style.opacity = '0';
      el.style.transform = 'translateY(10px)';
      el.style.transition = 'opacity 500ms ease-out, transform 500ms ease-out';

      el.innerHTML = `
        <div class="glass-panel px-3 py-1.5 border-l-2 border-[#D4C3A3] flex items-center gap-2 rounded-sm">
          <span class="font-label text-[10px] text-[#f1dfbe] uppercase whitespace-nowrap">[${escapeHTML(label.source)}]</span>
          <span class="font-body text-sm text-white leading-tight">${escapeHTML(label.text)}</span>
        </div>
        <div class="ar-line mt-0.5"></div>
      `;

      container.appendChild(el);

      // Stagger each label's entrance
      setTimeout(() => {
        el.style.opacity = '1';
        el.style.transform = 'translateY(0)';
      }, STAGGER_MS * i + 30);
    });
  }, 300);
}

export function clearARLabels() {
  if (exitTimer) { clearTimeout(exitTimer); exitTimer = null; }
  const container = document.getElementById('ar-overlay');
  if (container) container.innerHTML = '';
  currentLabels = [];
}

// ═══════════════════════════════════════════
// Subtitles
// ═══════════════════════════════════════════

let subtitleTimer = null;

export function showSubtitle(text) {
  const el = document.getElementById('subtitle-text');
  const loader = document.getElementById('loading-indicator');
  if (!el) return;

  if (loader) loader.classList.add('hidden');
  if (subtitleTimer) clearTimeout(subtitleTimer);

  // Crossfade: fade out current text
  el.style.transition = 'opacity 300ms ease-out';
  el.style.opacity = '0';

  subtitleTimer = setTimeout(() => {
    el.textContent = text;
    el.style.transition = 'opacity 500ms ease-in';
    el.style.opacity = '1';
  }, 300);
}

export function hideSubtitle() {
  const el = document.getElementById('subtitle-text');
  if (el) {
    el.style.transition = 'opacity 300ms ease-out';
    el.style.opacity = '0';
    setTimeout(() => { el.textContent = ''; }, 300);
  }
  if (subtitleTimer) {
    clearTimeout(subtitleTimer);
    subtitleTimer = null;
  }
}

// ── Utilities ──

function escapeHTML(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
