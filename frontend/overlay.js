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

export function renderARLabels(labels, onLabelClick = null) {
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

      if (onLabelClick) {
        el.style.pointerEvents = 'auto';
        el.style.cursor = 'pointer';
      }

      el.innerHTML = `
        <div class="glass-panel px-3 py-1.5 border-l-2 border-[#D4C3A3] flex items-center gap-2 rounded-sm">
          ${onLabelClick ? '<span class="landmark-ping w-2 h-2 rounded-full bg-primary flex-shrink-0"></span>' : ''}
          <span class="font-label text-[10px] text-[#f1dfbe] uppercase whitespace-nowrap">[${escapeHTML(label.source)}]</span>
          <span class="font-body text-sm text-white leading-tight">${escapeHTML(label.text)}</span>
        </div>
      `;

      if (onLabelClick) {
        el.addEventListener('click', () => onLabelClick(label));
      }

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
  const container = document.getElementById('caption-container') || el?.parentElement;
  const loader = document.getElementById('loading-indicator');
  if (!el) return;

  if (loader) loader.style.display = 'none';
  if (subtitleTimer) { clearTimeout(subtitleTimer); subtitleTimer = null; }

  el.textContent = text;
  if (container) { container.style.opacity = '1'; }
  else { el.style.opacity = '1'; }

  // Auto-hide after 4s of no updates
  subtitleTimer = setTimeout(() => hideSubtitle(), 4000);
}

export function hideSubtitle() {
  const el = document.getElementById('subtitle-text');
  const container = document.getElementById('caption-container') || el?.parentElement;
  if (container) {
    container.style.opacity = '0';
    setTimeout(() => { if (el) el.textContent = ''; }, 300);
  } else if (el) {
    el.style.opacity = '0';
    setTimeout(() => { el.textContent = ''; }, 300);
  }
  if (subtitleTimer) { clearTimeout(subtitleTimer); subtitleTimer = null; }
}

// ── Utilities ──

function escapeHTML(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
