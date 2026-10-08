import {STAGES, setDemoStatus, safeUrl, escapeHtml as esc, currentCounts} from './model.mjs';

const root = document.getElementById('tracker');
const boot = window.TRACKER_BOOTSTRAP;
const $ = selector => root.querySelector(selector);
const label = s => s ? s[0].toUpperCase() + s.slice(1) : 'Unknown';
const sourceLabel = s => ({queue: 'Discovery queue', email: 'Mailbox inference', manual: 'Manual update'}[s] || 'Unknown');
const groups = [['To review', ['ready', 'reviewing']], ['In progress', ['applied', 'assessment', 'interview']], ['Offer', ['offer']], ['Closed', ['rejected', 'dismissed']]];
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
const reduced = () => motionPreference.matches;
let snapshot = null, view = 'board', query = '', filter = null, trigger = null;
let busy = false, saving = false, paused = false, heroVisible = true, animationTimer = null, pollTimer = null;
let journeyAnimations = [], selectedKey = null;
const nodes = new Map();
const dialog = $('#details');
const content = $('.content');
const flow = $('.flow');
const isDemo = boot?.mode === 'demo';
const statusMessage = message => { $('#announce').textContent = message; };
const dateLabel = iso => {
  if (!iso) return 'Not recorded';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? String(iso) : date.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
};

async function jsonRequest(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, {...options, signal: controller.signal, cache: 'no-store', credentials: 'same-origin'});
    const value = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(value.error || `The tracker returned ${response.status}. Try refreshing.`);
    return value;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The tracker took too long to respond. Please try again.');
    throw error;
  } finally { clearTimeout(timeout); }
}

function applySnapshot(next, animate = true) {
  if (!next || !Array.isArray(next.items) || !next.items.every(item => typeof item.key === 'string' && STAGES.includes(item.status))) {
    throw new Error('The tracker returned an unsupported data format.');
  }
  snapshot = next;
  const keys = new Set(next.items.map(item => item.key));
  for (const [key, node] of nodes) if (!keys.has(key)) { node.remove(); nodes.delete(key); }
  render(animate);
  summaries();
  drawJourney(false);
  $('#load-error').hidden = true;
  content.setAttribute('aria-busy', 'false');
  $('#snapshot-label').textContent = isDemo ? 'FICTIONAL SNAPSHOT · OCT 2026' : 'LOCAL TRACKER';
  $('#service-status').textContent = isDemo
    ? 'Fictional demo · Sample scores and mailbox events. Status changes reset when you reload.'
    : `Records loaded ${dateLabel(next.snapshot_at)} · Queue ${next.queue_updated_at ? 'updated ' + dateLabel(next.queue_updated_at) : 'awaiting its first sync'}`;
  const warnings = next.warnings || [];
  $('#service-warnings').hidden = !warnings.length;
  $('#service-warnings').innerHTML = '<ul>' + warnings.map(w => `<li>${esc(w)}</li>`).join('') + '</ul>';
}

async function load(animate = false) {
  if (busy) return;
  busy = true;
  $('#refresh-data').disabled = true;
  try {
    if (!['demo', 'local'].includes(boot?.mode)) throw new Error('The workspace could not start. Reload the page.');
    applySnapshot(isDemo ? structuredClone(boot.snapshot) : await jsonRequest('api/tracker'), animate);
  } catch (error) {
    const notice = $('#load-error');
    notice.hidden = false;
    notice.innerHTML = `${snapshot ? 'Showing the last loaded records. ' : ''}${esc(error.message)} <button class="ghost">Try again ↗</button>`;
    notice.querySelector('button').onclick = () => load();
    content.setAttribute('aria-busy', 'false');
    if (!snapshot) content.innerHTML = '<div class="empty">Your records will appear when the tracker is available.</div>';
  } finally { busy = false; $('#refresh-data').disabled = false; }
}

function card(item) {
  let node = nodes.get(item.key);
  if (!node) {
    node = document.createElement('button');
    node.type = 'button'; node.className = 'job'; node.dataset.key = item.key;
    node.onclick = () => openDetails(item.key, node);
    nodes.set(item.key, node);
  }
  const assessment = item.assessment || {};
  const score = typeof assessment.score === 'number' ? `${assessment.score}/100 match` : 'Not scored';
  const flags = assessment.flags || [];
  node.setAttribute('aria-label', `${item.company}, ${item.title}, ${item.status}. Open details`);
  node.innerHTML = `${item.priority_program ? `<div class="prioritytag">PRIORITY · ${item.priority_program.official_source ? 'OFFICIAL SOURCE' : 'VERIFY SOURCE'}</div>` : ''}
    <div class="company"><span class="monogram" aria-hidden="true">${esc((item.company || '?')[0])}</span>${esc(item.company)}</div>
    <div class="role">${esc(item.title)}</div><div class="location">${view === 'table' ? label(item.status) + ' · ' : ''}${esc(item.location || 'Location not recorded')}</div>
    <div class="scoreline"><strong>${esc(score)}</strong><span>${esc(sourceLabel(item.status_source))}</span></div>
    ${flags.length ? `<div class="flag">Verify: ${esc(flags[0].replace(/^verify\s+/i, ''))}</div>` : ''}
    <div class="next"><span>${item.last_update ? 'Email · ' + esc(item.last_update) : 'Discovered · ' + esc(item.first_seen?.slice(0, 10) || 'date unavailable')}</span><span aria-hidden="true">↗</span></div>`;
  return node;
}

function render(animate = true) {
  if (!snapshot) return;
  const before = new Map([...nodes].filter(([, n]) => n.isConnected).map(([key, n]) => [key, n.getBoundingClientRect()]));
  const visible = snapshot.items.filter(item => (!filter || filter.includes(item.status)) && `${item.company} ${item.title}`.toLowerCase().includes(query.toLowerCase()));
  content.replaceChildren();
  const box = document.createElement('div'); box.className = view; content.append(box);
  if (view === 'board') {
    STAGES.filter(stage => !filter || filter.includes(stage)).forEach(stage => {
      const lane = document.createElement('section'); lane.className = 'lane'; lane.setAttribute('aria-label', label(stage));
      const items = visible.filter(item => item.status === stage);
      lane.innerHTML = `<div class="lanehead"><span>${label(stage)}</span><span>${String(items.length).padStart(2, '0')}</span></div>`;
      box.append(lane); items.forEach(item => lane.append(card(item)));
      if (!items.length) lane.insertAdjacentHTML('beforeend', '<p class="empty">No records</p>');
    });
  } else if (view === 'table') {
    box.innerHTML = '<div class="tablehead" aria-hidden="true"><span>Company</span><span>Role</span><span>Stage / location</span><span>Match / source</span><span>Latest record</span></div>';
    visible.forEach(item => box.append(card(item)));
  } else {
    box.innerHTML = '<p class="activitynote">Recorded mailbox updates. Dates show when messages were received, not scheduled interviews.</p>';
    const events = visible.flatMap(item => (item.events || []).map(event => ({item, event}))).sort((a, b) => String(b.event.date_iso || b.event.date || '').localeCompare(String(a.event.date_iso || a.event.date || '')));
    events.forEach(({item, event}) => {
      const row = document.createElement('div'); row.className = 'activityrow';
      row.innerHTML = `<time>${esc(event.date || event.date_iso)}</time><button class="recordbutton">${esc(item.company)}<small>${esc(event.subject)}</small></button><span class="eventstage">${esc(label(event.stage))}</span>`;
      row.querySelector('button').onclick = e => openDetails(item.key, e.currentTarget); box.append(row);
    });
    if (!events.length) box.insertAdjacentHTML('beforeend', '<div class="empty">No mailbox events recorded for these matches.</div>');
  }
  if (!visible.length) content.innerHTML = '<div class="empty">No matching records. Try another company, role or stage.</div>';
  root.querySelectorAll('[data-view]').forEach(button => button.setAttribute('aria-pressed', button.dataset.view === view));
  $('#group-filter').hidden = !filter;
  $('#group-filter').textContent = filter ? filter.map(label).join(' + ') + ' · Clear ×' : '';
  $('#stage-filter').value = filter?.length === 1 ? filter[0] : '';
  if (animate && !reduced() && view !== 'activity') visible.forEach((item, i) => {
    const node = nodes.get(item.key), from = before.get(item.key), to = node.getBoundingClientRect();
    node.getAnimations().forEach(animation => animation.cancel());
    node.animate(from ? [{transform: `translate(${from.left - to.left}px,${from.top - to.top}px)`, opacity: .65}, {transform: 'translate(0,0)', opacity: 1}] : [{transform: 'translateY(14px)', opacity: 0}, {transform: 'translateY(0)', opacity: 1}], {duration: 520, delay: from ? 0 : Math.min(i * 22, 140), easing: 'cubic-bezier(.22,1,.36,1)'});
  });
  statusMessage(`${label(view)} view. ${visible.length} records.`);
}

function summaries() {
  const items = snapshot.items, counts = currentCounts(items);
  $('#record-count').textContent = `${items.length} TRACKED RECORDS · CURRENT STATUS`;
  const captions = $('.stagecaptions');
  if (!captions.children.length) groups.forEach(([name, statuses]) => {
    const button = document.createElement('button'); button.innerHTML = '<b></b>' + name;
    button.onclick = () => { filter = statuses; render(); };
    captions.append(button);
  });
  groups.forEach(([name, statuses], i) => {
    const count = items.filter(item => statuses.includes(item.status)).length;
    captions.children[i].querySelector('b').textContent = String(count).padStart(2, '0');
    captions.children[i].setAttribute('aria-label', `Show ${name}: ${count} records`);
  });
  const bars = $('.bars');
  if (!bars.children.length) STAGES.forEach(() => bars.append(document.createElement('span')));
  const max = Math.max(1, ...Object.values(counts));
  STAGES.forEach((s, i) => { bars.children[i].style.height = `${counts[s] / max * 100}%`; });
  bars.setAttribute('aria-label', STAGES.map(s => `${label(s)}: ${counts[s]}`).join(', '));
  const ready = items.filter(item => item.status === 'ready');
  $('.signal').innerHTML = `<b>${ready.length} matches ready for review.</b> ${ready.filter(item => item.assessment?.flags?.length).length} with verification flags. Match scores describe profile fit, not hiring probability.`;
  $('#review-top').disabled = !ready.length;
}

function motionAllowed() { return !paused && !reduced() && !document.hidden && heroVisible; }
function scheduleJourney() {
  clearTimeout(animationTimer);
  if (snapshot && motionAllowed()) animationTimer = setTimeout(() => drawJourney(true), 5000);
}
function drawJourney(animate = true) {
  scheduleJourney();
  journeyAnimations.forEach(a => a.cancel()); journeyAnimations = [];
  flow.replaceChildren();
  if (!snapshot) return;
  const width = Math.max(280, flow.clientWidth), height = width < 650 ? 145 : 185;
  flow.setAttribute('viewBox', `0 0 ${width} ${height}`);
  flow.style.height = `${height}px`;
  const ns = 'http://www.w3.org/2000/svg';
  const drawn = groups.flatMap(([, statuses], group) => snapshot.items.filter(item => statuses.includes(item.status)).slice(0, 40).map((item, row, peers) => ({item, group, row, size: peers.length})));
  drawn.forEach(({group, row, size}, i) => {
    const x = width * (.065 + group * .265), y = 18 + row * Math.min(18, (height - 36) / Math.max(1, size - 1));
    const startY = 12 + i / Math.max(1, drawn.length - 1) * (height - 24);
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', `M 5 ${startY} C ${x * .42} ${startY}, ${x * .65} ${y}, ${x} ${y}`); flow.append(path);
    const dot = document.createElementNS(ns, 'circle'); dot.setAttribute('r', width < 650 ? '2.5' : '4'); dot.setAttribute('cx', x); dot.setAttribute('cy', y); flow.append(dot);
    if (animate && motionAllowed()) {
      const length = path.getTotalLength(), delay = Math.min(i * 25, 375);
      const options = {duration: 1400, delay, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'both'};
      journeyAnimations.push(path.animate([{strokeDasharray: length, strokeDashoffset: length}, {strokeDasharray: length, strokeDashoffset: 0}], options));
      const frames = Array.from({length: 45}, (_, k) => { const p = path.getPointAtLength(length * k / 44); return {transform: `translate(${p.x - x}px,${p.y - y}px)`, opacity: k === 0 ? 0 : 1}; });
      journeyAnimations.push(dot.animate(frames, options));
    }
  });
  $('#journey-note').textContent = drawn.length < snapshot.items.length ? 'Up to 40 points per group; counts are exact. Current status, not history.' : 'One point, one record. Current status, not transition history.';
  flow.setAttribute('aria-label', groups.map(([name, statuses]) => `${name}: ${snapshot.items.filter(item => statuses.includes(item.status)).length}`).join('. ') + '. Decorative motion does not represent historical transitions.');
}

function closeDetails() {
  if (saving) return;
  dialog.close(); selectedKey = null;
  if (trigger?.isConnected) trigger.focus(); else $('#review-top').focus();
}
function openDetails(key, button) {
  const item = snapshot.items.find(record => record.key === key);
  if (!item) return;
  selectedKey = key; trigger = button;
  const assessment = item.assessment || {}, reasons = assessment.reasons || [], flags = assessment.flags || [];
  const url = safeUrl(item.url);
  dialog.innerHTML = `<div class="drawerhead"><div class="company"><span class="monogram" aria-hidden="true">${esc((item.company || '?')[0])}</span>${esc(item.company)}</div><button class="close" aria-label="Close details">×</button></div>
    <h3 id="detail-title">${esc(item.title)}</h3><div class="location">${esc(item.location || 'Location not recorded')}</div>
    ${url && !isDemo ? `<a class="record-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Open employer application ↗</a>` : ''}
    <dl><dt>Current status</dt><dd>${esc(label(item.status))}</dd><dt>Status source</dt><dd>${esc(sourceLabel(item.status_source))}</dd><dt>Profile match</dt><dd>${typeof assessment.score === 'number' ? assessment.score + '/100' : 'Not scored'}</dd></dl>
    ${item.priority_program ? `<p class="flag">Priority: ${esc(item.priority_program.name)} · ${item.priority_program.official_source ? 'Official source' : 'Verify source'}</p>` : ''}
    ${reasons.length ? '<h4>Why this match</h4><ul>' + reasons.map(reason => '<li>' + esc(reason) + '</li>').join('') + '</ul>' : '<p class="notice">No discovery assessment is recorded.</p>'}
    ${flags.length ? '<h4>Verify before applying</h4><ul>' + flags.map(flag => '<li>' + esc(flag) + '</li>').join('') + '</ul>' : ''}
    <h4>Recorded mailbox activity</h4>${item.events?.length ? item.events.map(event => `<div class="event">${esc(event.subject)}<small>${esc(event.date || event.date_iso)} · ${esc(event.mailbox_account)}</small></div>`).join('') : '<p class="notice">No mailbox events recorded.</p>'}
    <form id="status-form"><label for="status-select">Set status manually</label><select id="status-select" name="status">${STAGES.map(stage => `<option value="${stage}" ${stage === item.status ? 'selected' : ''}>${label(stage)}</option>`).join('')}</select><button class="primary save" type="submit">${isDemo ? 'Save demo status' : 'Save status'}</button><div class="error-message" id="save-error" role="alert" hidden></div></form>
    <p class="notice">${isDemo ? 'Fictional record. Changes reset on reload.' : 'Changes are saved on this Mac.'} Manual updates do not create mailbox events. Existing email stages take precedence over Ready and Reviewing.</p>`;
  dialog.querySelector('.close').onclick = closeDetails;
  dialog.querySelector('form').onsubmit = async event => {
    event.preventDefault(); if (saving) return;
    const status = dialog.querySelector('select').value, saveKey = selectedKey;
    saving = true;
    dialog.querySelectorAll('button,select').forEach(control => { control.disabled = true; });
    dialog.querySelector('.save').textContent = 'Saving…';
    $('#save-error').hidden = true;
    try {
      const next = isDemo ? setDemoStatus(snapshot, saveKey, status) : await jsonRequest(`api/status/${encodeURIComponent(saveKey)}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': boot.csrfToken}, body: JSON.stringify({status})});
      applySnapshot(next);
      const saved = next.items.find(item => item.key === saveKey);
      saving = false; closeDetails();
      const message = saved?.status !== status ? `Mailbox history keeps this record at ${label(saved?.status)}.` : `Status saved as ${label(status)}${isDemo ? ' in the demo' : ''}.`;
      statusMessage(message); $('#service-status').textContent += ' · ' + message;
    } catch (error) {
      $('#save-error').textContent = error.message; $('#save-error').hidden = false;
      statusMessage('Status could not be saved.');
    } finally {
      saving = false;
      dialog.querySelectorAll('button,select').forEach(control => { control.disabled = false; });
      dialog.querySelector('.save').textContent = isDemo ? 'Save demo status' : 'Save status';
    }
  };
  dialog.showModal(); dialog.scrollTop = 0;
  if (!reduced()) dialog.animate([{transform: 'translateX(45px)', opacity: 0}, {transform: 'translateX(0)', opacity: 1}], {duration: 420, easing: 'cubic-bezier(.22,1,.36,1)'});
  dialog.querySelector('.close').focus();
}

dialog.addEventListener('cancel', event => { event.preventDefault(); closeDetails(); });
dialog.addEventListener('click', event => {
  const box = dialog.getBoundingClientRect();
  if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) closeDetails();
});
root.querySelectorAll('[data-view]').forEach(button => button.onclick = () => { view = button.dataset.view; render(); });
$('#search').oninput = event => { query = event.target.value; render(); };
STAGES.forEach(stage => { const option = document.createElement('option'); option.value = stage; option.textContent = label(stage); $('#stage-filter').append(option); });
$('#stage-filter').onchange = event => { filter = event.target.value ? [event.target.value] : null; render(); };
$('#group-filter').onclick = () => { filter = null; render(); };
$('#review-top').onclick = event => {
  const best = snapshot?.items.filter(item => item.status === 'ready').sort((a, b) => (Number(b.assessment?.score) || 0) - (Number(a.assessment?.score) || 0))[0];
  if (best) openDetails(best.key, event.currentTarget);
};
$('#review-ready').onclick = () => { filter = ['ready']; render(); };
$('#refresh-data').onclick = () => load(true);
$('#reset-demo').onclick = () => { query = ''; filter = null; $('#search').value = ''; load(true); };
function syncMotionControl() {
  $('#motion-toggle').disabled = reduced();
  $('#motion-toggle').textContent = reduced() ? 'Reduced motion' : paused ? 'Resume motion' : 'Pause motion';
  $('#motion-toggle').setAttribute('aria-pressed', paused || reduced());
}
$('#motion-toggle').onclick = () => { paused = !paused; syncMotionControl(); drawJourney(false); };
motionPreference.addEventListener('change', () => { syncMotionControl(); drawJourney(false); });
document.addEventListener('visibilitychange', () => { if (document.hidden) journeyAnimations.forEach(a => a.finish()); scheduleJourney(); });
new IntersectionObserver(entries => { heroVisible = entries[0].isIntersecting; scheduleJourney(); }, {threshold: .1}).observe($('.hero'));
let previousWidth = 0;
new ResizeObserver(entries => { const width = entries[0].contentRect.width; if (Math.abs(width - previousWidth) > 1) { previousWidth = width; drawJourney(false); } }).observe(flow);
window.addEventListener('pagehide', () => { clearTimeout(animationTimer); clearInterval(pollTimer); });
window.addEventListener('pageshow', () => { scheduleJourney(); startPolling(); });
function startPolling() {
  clearInterval(pollTimer);
  if (!isDemo) pollTimer = setInterval(() => { if (!document.hidden && !dialog.open && !saving) load(); }, 60000);
}

$('#mode-label').textContent = isDemo ? 'Fictional demo' : 'Local tracker';
$('#footer-mode').textContent = isDemo ? 'Fictional records · No account connected' : 'Private workspace · Saved on this Mac';
$('#reset-demo').hidden = !isDemo;
$('#refresh-data').hidden = isDemo;
const params = new URLSearchParams(location.search);
query = params.get('q') || ''; $('#search').value = query;
if (STAGES.includes(params.get('stage'))) filter = [params.get('stage')];
syncMotionControl();
await load();
drawJourney(true);
if (!reduced()) root.querySelectorAll('.eyebrow,h1,.intro').forEach((element, i) => element.animate([{transform: 'translateY(24px)', opacity: 0, filter: 'blur(5px)'}, {transform: 'translateY(0)', opacity: 1, filter: 'blur(0)'}], {duration: 850, delay: i * 100, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'both'}));
startPolling();
