'use strict';
/* Routing, top bar, live events (SSE) and boot. */

const PAGES = ['workflow', 'browse', 'library', 'tasks', 'watches', 'accounts', 'connect', 'settings'];

function route() {
  const page = (location.hash || '#workflow').slice(1);
  S.page = PAGES.includes(page) ? page : 'workflow';
  $$('#nav a').forEach(a => a.classList.toggle('active', a.dataset.page === S.page));
  $$('.page').forEach(p => p.classList.toggle('show', p.id === `page-${S.page}`));
  $('#page-title').textContent = t('page.' + S.page);
  $('#page-crumb').textContent = `TG AGENT / ${S.page.toUpperCase()}`;
  if (S.page === 'workflow') { renderWfList(); renderWfMain(); }
  if (S.page === 'browse') initBrowse();
  if (S.page === 'library') initLibrary();
  if (S.page === 'connect') renderConnect();
  if (S.page === 'settings') fillSettings();
  render();
}

let rafPending = false;
function render() {
  if (rafPending) return;
  rafPending = true;
  requestAnimationFrame(() => {
    rafPending = false;
    renderTop();
    if (S.page === 'tasks') renderTasks();
    if (S.page === 'accounts') renderAccounts();
    if (S.page === 'watches') renderWatches();
  });
}

function renderTop() {
  const st = S.stats;
  $('#top-speed').textContent = `${size(st.speed || 0)}/s`;
  const win = $('#top-window');
  const closed = st.window_open === false;
  win.hidden = !closed && !st.speed_limit_kbps;
  win.querySelector('span').textContent = closed ? t('top.window') : t('top.limit', { n: size(st.speed_limit_kbps * 1024) + '/s' });
  const up = $('#update-note');
  up.classList.toggle('show', !!S.update?.newer);
  if (S.update?.newer) { up.textContent = t('update.available', { v: S.update.version }); up.href = S.update.url; }
  $('#top-active span').textContent = `${st.running || 0} / ${st.queued || 0}`;
  const def = S.accounts.find(a => a.is_default) || S.accounts[0];
  $('#top-account').innerHTML = def
    ? `${avatar(def.name)}<span>${esc(def.me?.username ? '@' + def.me.username : def.name)}</span>${statusTag(def.status)}`
    : `<span class="muted">${t('acc.none')}</span>`;
  const badge = (id, n, txt) => { const b = $(id); b.textContent = txt ?? n; b.classList.toggle('show', !!n); };
  badge('#nav-tasks-badge', (st.running || 0) + (st.queued || 0));
  badge('#nav-wf-badge', S.approvals.length);
  badge('#nav-watch-badge', S.watches.filter(w => w.pending_approval).length);
  const needLogin = S.accounts.filter(a => a.status !== 'ready').length;
  badge('#nav-acc-badge', needLogin || !S.accounts.length ? 1 : 0, S.accounts.length ? needLogin : '!');
}

function setLang(lang) {
  LANG = lang === 'zh' ? 'zh' : 'en';
  try { localStorage.setItem('tga-lang', LANG); } catch (e) {}
  applyI18n();
  route();
}

/* ------------------------------------------------------------ data */
async function loadState() {
  const st = await api('/api/state');
  S.accounts = st.accounts; S.settings = st.settings; S.stats = st.stats; S.port = st.port;
  S.paths = { ...st.paths, platform: st.platform };
  S.tasks = new Map(st.tasks.map(x => [x.id, x]));
  S.activity = new Map(st.activity.map(e => [e.id, e]));
  S.workflows = new Map(st.workflows.map(w => [w.id, w]));
  S.approvals = st.approvals; S.watches = st.watches; S.update = st.update || {};
  const tools = await api('/api/tools');
  S.toolsMeta = Object.fromEntries(tools.map(x => [x.name, x]));
  LANG = st.settings.language === 'zh' ? 'zh' : 'en';
  applyI18n();
  renderApprovals();
  const active = [...S.workflows.values()].filter(w => w.status === 'active').sort((a, b) => b.updated - a.updated)[0];
  const latest = active || [...S.workflows.values()].sort((a, b) => b.updated - a.updated)[0];
  if (latest) selectWorkflow(latest.id);
}
async function loadAccounts() {
  try { S.accounts = await api('/api/accounts'); render(); if (S.page === 'browse') initBrowse(); } catch (e) { /* offline */ }
}

let es = null;
function connectEvents() {
  if (es) es.close();
  es = new EventSource('/api/events');
  const conn = $('#conn');
  es.onopen = () => { conn.className = 'conn ok'; $('#conn-text').textContent = t('conn.ok'); };
  es.onerror = () => { conn.className = 'conn bad'; $('#conn-text').textContent = t('conn.bad'); };
  es.addEventListener('activity', e => {
    const ev = JSON.parse(e.data);
    S.activity.set(ev.id, ev);
    if (S.activity.size > 600) [...S.activity.keys()].sort((a, b) => a - b).slice(0, 100).forEach(k => S.activity.delete(k));
    if (ev.batch || ev.watch_id) refreshApprovals();
    if (S.page === 'workflow' && S.wf.view === 'log') renderWfMain();
  });
  es.addEventListener('workflow', e => {
    const w = JSON.parse(e.data);
    const prev = S.workflows.get(w.id);
    if (prev && prev.status === 'active' && w.status !== 'active' && w.explicit) notify(t('n.wf'), w.title);
    onWorkflowEvent(w);
  });
  es.addEventListener('update', e => { S.update = JSON.parse(e.data); render(); });
  es.addEventListener('step', e => onStepEvent(JSON.parse(e.data)));
  es.addEventListener('task', e => {
    const tk = JSON.parse(e.data);
    const prev = S.tasks.get(tk.id);
    S.tasks.set(tk.id, tk);
    if ((prev?.status === 'approval') !== (tk.status === 'approval')) api('/api/approvals').then(a => { S.approvals = a; renderApprovals(); render(); });
    if (tk.kind === 'download' && prev && prev.status !== tk.status) {
      if (tk.status === 'done') notifyBatch('done', tk.title);
      if (tk.status === 'failed') notifyBatch('failed', tk.title);
      if (tk.status === 'approval' && prev.status !== 'approval') notifyBatch('approval', tk.chat_title);
    }
    onTaskForFlow(tk);
    render();
  });
  es.addEventListener('stats', e => {
    S.stats = JSON.parse(e.data);
    S.speedHist.push(S.stats.speed || 0); S.speedHist.shift();
    render();
  });
}

/* ------------------------------------------------------------ desktop notifications */
function notifyEnabled() {
  try { return localStorage.getItem('tga-notify') === '1' && 'Notification' in window && Notification.permission === 'granted'; } catch (e) { return false; }
}
function setNotify(on) { try { localStorage.setItem('tga-notify', on ? '1' : '0'); } catch (e) {} }
function notify(title, body) {
  if (!notifyEnabled()) return;
  try { new Notification(title, { body, icon: '/assets/icon.svg', tag: title }); } catch (e) {}
}
const pending = { done: [], failed: [], approval: [] };
let notifyTimer = null;
function notifyBatch(kind, name) {
  pending[kind].push(name);
  clearTimeout(notifyTimer);
  notifyTimer = setTimeout(() => {
    for (const k of Object.keys(pending)) {
      const items = pending[k];
      if (!items.length) continue;
      notify(t('n.' + k) + (items.length > 1 ? ` ×${items.length}` : ''), items.slice(0, 3).join('\n'));
      pending[k] = [];
    }
  }, 2500);
}

/* ------------------------------------------------------------ boot */
function bindGlobal() {
  window.addEventListener('hashchange', route);
  $('#theme-btn').onclick = () => {
    const cur = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = cur;
    try { localStorage.setItem('tga-theme', cur); } catch (e) {}
    $('#theme-btn').innerHTML = icon(cur === 'light' ? 'moon' : 'sun');
  };
  $('#lang-switch').onclick = async e => {
    const lang = e.target.dataset.lang; if (!lang || lang === LANG) return;
    try { S.settings = await post('/api/settings', { language: lang }); } catch (err) { /* still switch locally */ }
    setLang(lang);
  };
  $('#modal-back').onclick = e => { if (e.target.id === 'modal-back') closeModal(); };
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') return closeModal();
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable || e.ctrlKey || e.metaKey || e.altKey) return;
    const n = Number(e.key);
    if (n >= 1 && n <= PAGES.length) location.hash = PAGES[n - 1];
  });
  $('#login-form').onsubmit = async e => {
    e.preventDefault();
    try {
      await post('/api/login', { token: $('#login-token').value.trim() });
      $('#login-screen').classList.remove('show');
      await start();
    } catch (err) { toast(t('login.bad'), false); }
  };
}

async function start() {
  await loadState();
  route();
  connectEvents();
}

(async function boot() {
  try { LANG = localStorage.getItem('tga-lang') || (navigator.language.startsWith('zh') ? 'zh' : 'en'); } catch (e) {}
  applyI18n();
  hydrateIcons();
  $('#theme-btn').innerHTML = icon(document.documentElement.dataset.theme === 'light' ? 'moon' : 'sun');
  bindGlobal(); bindWorkflow(); bindBrowse(); bindLibrary(); bindTasks(); bindWatches(); bindAccounts(); bindConnect(); bindSettings();
  try { await start(); } catch (e) { if (!$('#login-screen').classList.contains('show')) toast(e.message, false); }
  setInterval(loadAccounts, 5000);
  setInterval(() => { if (S.page === 'workflow' && S.wf.view === 'flows') renderWfList(); }, 30000);
})();
