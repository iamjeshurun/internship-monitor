export const STAGES = ['ready', 'reviewing', 'applied', 'assessment', 'interview', 'offer', 'rejected', 'dismissed'];
const order = {ready: 0, reviewing: 1, applied: 2, assessment: 3, interview: 4, offer: 5, rejected: 5, dismissed: 6};

// Mirrors the backend's manual-status precedence. Email events are preserved.
export function setDemoStatus(snapshot, key, status) {
  if (!STAGES.includes(status)) throw new Error('Choose a valid application status.');
  const next = structuredClone(snapshot);
  const item = next.items.find(record => record.key === key);
  if (!item) throw new Error('This record is no longer available.');
  item.status = status;
  item.status_source = 'manual';
  if (['ready', 'reviewing'].includes(status) && item.events?.length) {
    const events = [...item.events].sort((a, b) => {
      const time = String(a.date_iso || a.date || '').localeCompare(String(b.date_iso || b.date || ''));
      return time || (order[a.stage] ?? 0) - (order[b.stage] ?? 0);
    });
    item.status = events.at(-1).stage || 'applied';
    item.status_source = 'email';
  }
  return next;
}

export function safeUrl(raw) {
  try {
    const url = new URL(raw);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

export function currentCounts(items) {
  return Object.fromEntries(STAGES.map(stage => [stage, items.filter(item => item.status === stage).length]));
}
