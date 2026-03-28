// ═══════════════════════════════════════════
// Subtitles / Captions
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
