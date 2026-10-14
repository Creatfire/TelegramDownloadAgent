'use strict';
/* Workflows page: list of sessions' workflows, the step graph with data-flow edges, step details. */

function briefArgs(args) {
  const out = [];
  for (const [k, v] of Object.entries(args || {})) {
    if (v === '' || v == null || v === false || (Array.isArray(v) && !v.length) || k === 'account') continue;
    const s = Array.isArray(v) ? v.slice(0, 3).join(', ') + (v.length > 3 ? ` …(+${v.length - 3})` : '') : String(v);
    out.push(`${k}=${s.length > 60 ? s.slice(0, 60) + '…' : s}`);
  }
  return out.join('  ');
}

/* ------------------------------------------------------------ approvals */
function renderApprovals() {
  const html = S.approvals.map(a => `<div class="approval">${icon('shield')}
      <div class="ap-main"><div class="ap-title">${esc(t('ap.title', { agent: a.source, n: a.count, size: size(a.size) }))}</div>
        <div class="ap-sub">${esc(a.chat_title)} · ${esc(a.sample.join(' · '))}</div></div>
      <button class="btn sm ghost" data-ap="${a.batch}" data-ok="0">${t('ap.reject')}</button>
      <button class="btn sm primary" data-ap="${a.batch}" data-ok="1">${icon('check')}${t('ap.approve')}</button></div>`).join('')
    + S.watches.filter(w => w.pending_approval).map(w => `<div class="approval">${icon('eye')}
      <div class="ap-main"><div class="ap-title">${esc(t('ap.watch', { agent: w.source, chat: w.chat_title }))}</div>
        <div class="ap-sub">${esc(watchFilterText(w))} · ${t('watch.every', { n: w.interval_min })}</div></div>
      <button class="btn sm ghost" data-wap="${w.id}" data-ok="0">${t('ap.reject')}</button>
      <button class="btn sm primary" data-wap="${w.id}" data-ok="1">${icon('check')}${t('ap.approve')}</button></div>`).join('');
  $('#approvals').innerHTML = html;
  $('#approvals-2').innerHTML = html;
  $('#wf-layout').classList.toggle('with-approvals', !!html);
}
async function onApproval(e) {
  const b = e.target.closest('[data-ap],[data-wap]');
  if (!b) return;
  const ok = b.dataset.ok === '1';
  try {
    if (b.dataset.ap) await post(`/api/approvals/${b.dataset.ap}`, { approve: ok });
    else if (ok) await api(`/api/watches/${b.dataset.wap}`, { method: 'PATCH', body: { approve: true } });
    else await api(`/api/watches/${b.dataset.wap}`, { method: 'DELETE' });
    toast(ok ? t('ap.done') : t('ap.rejected'), ok);
    await refreshApprovals();
  } catch (err) { toast(err.message, false); }
}
async function refreshApprovals() {
  [S.approvals, S.watches] = await Promise.all([api('/api/approvals'), api('/api/watches')]);
  renderApprovals();
  render();
}

/* ------------------------------------------------------------ workflow list */
function renderWfList() {
  const box = $('#wf-items');
  const q = S.wf.q.toLowerCase();
  let items = [...S.workflows.values()].sort((a, b) => b.updated - a.updated);
  if (q) items = items.filter(w => (w.title || '').toLowerCase().includes(q) || (w.agent || '').toLowerCase().includes(q));
  if (!items.length) { box.innerHTML = `<div class="empty">${t('wf.none')}</div>`; return; }
  const today = new Date().toDateString();
  const groups = [[t('wf.active'), items.filter(w => w.status === 'active')],
                  [t('wf.today'), items.filter(w => w.status !== 'active' && new Date(w.updated * 1000).toDateString() === today)],
                  [t('wf.earlier'), items.filter(w => w.status !== 'active' && new Date(w.updated * 1000).toDateString() !== today)]];
  box.innerHTML = groups.filter(g => g[1].length).map(([label, list]) => `<div class="wf-group label">${label}</div>` + list.slice(0, 120).map(w => `
    <div class="wf-item ${S.wf.sel === w.id ? 'on' : ''}" data-id="${w.id}">
      <span class="st ${w.status}"></span>
      <div class="wf-item-title ${w.explicit ? '' : 'implicit'}">${esc(w.explicit ? w.title : t('wf.untitled'))}</div>
      <div class="wf-item-meta">${who(w.agent)}<span>${t('wf.steps', { n: w.steps })}</span><span>${ago(w.updated)}</span></div>
    </div>`).join('')).join('');
}

async function selectWorkflow(id, { keepNode = false } = {}) {
  if (S.wf.sel !== id) { S.wf.node = null; S.wf.nodeData = null; }
  S.wf.sel = id;
  if (!keepNode) $('#wf-layout').classList.toggle('no-detail', !S.wf.node);
  renderWfList();
  try {
    const d = await api(`/api/workflows/${id}`);
    if (S.wf.sel !== id) return;
    S.wf.data = d;
    for (const tk of d.tasks || []) S.tasks.set(tk.id, tk);
    renderWfMain();
  } catch (e) { $('#wf-main').innerHTML = `<div class="empty big">${icon('alert')}<p>${esc(e.message)}</p></div>`; }
}

/* ------------------------------------------------------------ workflow main */
function renderWfMain() {
  const main = $('#wf-main');
  if (S.wf.view === 'log') { renderLog(main); return; }
  const d = S.wf.data;
  if (!d) { main.innerHTML = `<div class="empty big">${icon('flow')}<p>${t(S.workflows.size ? 'wf.pick' : 'wf.none')}</p></div>`; return; }
  const w = { ...d.workflow, ...(S.workflows.get(d.workflow.id) || {}) };
  const end = w.ended || (w.status === 'active' ? Date.now() / 1000 : w.updated);
  main.innerHTML = `
    <div class="wf-head">
      <div class="wf-title"><span ${w.explicit ? 'contenteditable="plaintext-only" spellcheck="false" title="' + esc(t('wf.renameHint')) + '"' : ''} id="wf-title-text">${esc(w.explicit ? w.title : t('wf.untitled'))}</span>${wfTag(w.status)}
        <button class="icon-btn danger" id="wf-del" title="${t('wf.delete')}" style="margin-left:auto">${icon('trash')}</button></div>
      <div class="wf-meta">${who(w.agent)}<span>${t('wf.started')} ${clock(w.created)}</span><span>${t('wf.duration')} ${dur(end - w.created)}</span>
        <span>${t('wf.steps', { n: d.steps.length })}</span>${w.polls ? `<span>${t('wf.polls', { n: w.polls })}</span>` : ''}</div>
      ${w.explicit ? '' : `<div class="wf-goal muted small">${icon('info')} ${t('wf.implicitTip')}</div>`}
      ${w.goal ? `<div class="wf-goal">${esc(w.goal)}</div>` : ''}
      ${w.summary ? `<div class="wf-summary">${esc(w.summary)}</div>` : ''}
    </div>
    <div class="wf-canvas" id="wf-canvas"><svg class="edges" id="wf-edges"></svg><div class="flow" id="wf-flow"></div></div>`;
  renderFlow();
}

function stepTasks(step) {
  const ids = new Set(step.task_ids || []);
  return [...S.tasks.values()].filter(tk => tk.step_id === step.id || ids.has(tk.id));
}

function nodeHtml(s) {
  const tasks = stepTasks(s);
  const pending = tasks.filter(tk => tk.status === 'approval');
  const badges = [];
  if (s.polls) badges.push(`<span class="tag plain">${t('wf.polls', { n: s.polls })}</span>`);
  const dataParents = (s.parents || []).filter(p => p.kind === 'data').length;
  if (dataParents) badges.push(`<span class="tag info plain">${icon('link')}${dataParents}</span>`);
  let sub = '';
  if (tasks.length) {
    const shown = tasks.slice(0, 6);
    sub = `<div class="node-sub">${shown.map(tk => tk.kind === 'download' ? `
        <div class="sub-row">${kindIco(tk.file_kind)}<div class="sub-name" title="${esc(tk.title)}">${esc(tk.title)}</div>
          <div class="sub-prog">${tk.status === 'running' ? `${pct(tk).toFixed(0)}% · ${size(tk.speed)}/s` : t('task.' + tk.status)}
            <div class="bar ${tk.status}"><div style="width:${pct(tk)}%"></div></div></div></div>` : `
        <div class="sub-row">${kindIco('document')}<div class="sub-name">${esc(tk.title)}</div>
          <div class="sub-prog">${tk.status === 'done' ? esc(tk.note || t('task.done')) : tk.status === 'running' ? t('tasks.scanned', { n: tk.done }) : t('task.' + tk.status)}
            <div class="bar ${tk.status}"><div style="width:${tk.status === 'done' ? 100 : tk.status === 'running' ? 50 : 0}%"></div></div></div></div>`).join('')}
      ${tasks.length > shown.length ? `<div class="sub-more">${t('wf.more', { n: tasks.length - shown.length })}</div>` : ''}</div>`;
  }
  const approval = pending.length ? `<div class="node-approval">${icon('shield')}<span>${esc(t('ap.node', { n: pending.length, size: size(pending.reduce((x, tk) => x + tk.total, 0)) }))}</span>
      <button class="btn sm ghost" data-ap="${pending[0].batch}" data-ok="0">${t('ap.reject')}</button>
      <button class="btn sm primary" data-ap="${pending[0].batch}" data-ok="1">${t('ap.approve')}</button></div>` : '';
  return `<div class="node ${s.status} ${S.wf.node === s.id ? 'sel' : ''} ${S.wf.newIds.has(s.id) ? 'new' : ''}" data-id="${s.id}">
    <div class="node-head"><span class="node-seq">${s.status === 'running' ? icon('loader', 'spin') : s.seq}</span>
      <span class="node-title">${esc(toolTitle(s.tool))}</span><span class="node-tool">${esc(s.tool)}</span>
      <span class="node-time">${ms(s.ms)} · ${clock(s.ts)}</span></div>
    ${briefArgs(s.args) ? `<div class="node-args">${esc(briefArgs(s.args))}</div>` : ''}
    ${s.status === 'error' ? `<div class="node-error">${esc(s.error)}</div>` : s.summary ? `<div class="node-result">${esc(s.summary)}</div>` : ''}
    <div class="node-badges">${badges.join('')}</div>${approval}${sub}</div>`;
}

function renderFlow() {
  const flow = $('#wf-flow');
  if (!flow || !S.wf.data) return;
  const canvas = $('#wf-canvas');
  const nearBottom = canvas.scrollHeight - canvas.scrollTop - canvas.clientHeight < 80;
  const steps = S.wf.data.steps;
  const w = { ...S.wf.data.workflow, ...(S.workflows.get(S.wf.data.workflow.id) || {}) };
  const endCls = w.status === 'active' ? 'live' : w.status === 'failed' ? 'failed' : '';
  const endText = w.status === 'active' ? t('wf.waiting') : w.status === 'failed' ? t('wf.failedEnd') : w.status === 'done' ? t('wf.finished') : t('wf.idleEnd');
  flow.innerHTML = (steps.length ? steps.map(nodeHtml).join('') : `<div class="empty">${t('wf.noSteps')}</div>`)
    + `<div class="flow-end ${endCls}" id="wf-end"><span class="dot"></span>${endText}</div>`;
  S.wf.newIds.clear();
  requestAnimationFrame(() => {
    drawEdges();
    if (S.wf.follow && nearBottom) canvas.scrollTop = canvas.scrollHeight;
  });
}

function drawEdges() {
  const canvas = $('#wf-canvas'), svg = $('#wf-edges');
  if (!canvas || !svg || !S.wf.data) return;
  const nodes = {};
  $$('#wf-flow .node').forEach(el => { nodes[el.dataset.id] = el; });
  const steps = S.wf.data.steps;
  svg.setAttribute('width', canvas.scrollWidth);
  svg.setAttribute('height', canvas.scrollHeight);
  const sel = S.wf.node;
  const parts = [];
  let lane = 0;
  steps.forEach((s, i) => {
    const ce = nodes[s.id];
    if (!ce) return;
    for (const p of s.parents || []) {
      const pe = nodes[p.id];
      if (!pe) continue;
      const pi = steps.findIndex(x => x.id === p.id);
      const hl = sel && (sel === s.id || sel === p.id) ? ' hl' : '';
      const cls = `edge ${p.kind === 'data' ? 'data' : ''}${hl}`;
      if (pi === i - 1) {
        const x = ce.offsetLeft + 25;
        parts.push(`<path class="${cls}" d="M${x},${pe.offsetTop + pe.offsetHeight} V${ce.offsetTop}"/>`);
        if (p.kind === 'data') parts.push(`<circle class="edge-dot${hl}" cx="${x}" cy="${ce.offsetTop}" r="3"/>`);
      } else {
        // data dependency on an earlier, non-adjacent step: route through the left gutter
        const gx = ce.offsetLeft - 18 - (lane++ % 3) * 14, r = 8;
        const y1 = pe.offsetTop + 18, y2 = ce.offsetTop + 18, x1 = pe.offsetLeft, x2 = ce.offsetLeft;
        parts.push(`<path class="${cls}" d="M${x1},${y1} H${gx + r} Q${gx},${y1} ${gx},${y1 + r} V${y2 - r} Q${gx},${y2} ${gx + r},${y2} H${x2}"/>`);
        parts.push(`<circle class="edge-dot${hl}" cx="${x2}" cy="${y2}" r="3"/>`);
      }
    }
  });
  const last = steps.length ? nodes[steps[steps.length - 1].id] : null, end = $('#wf-end');
  if (last && end) {
    const x = last.offsetLeft + 25;
    parts.push(`<path class="edge" stroke-dasharray="3 4" d="M${x},${last.offsetTop + last.offsetHeight} V${end.offsetTop + 6}"/>`);
  }
  svg.innerHTML = parts.join('');
}

/* ------------------------------------------------------------ step detail */
function prettyJson(text) {
  if (text == null || text === '') return '';
  try { return JSON.stringify(typeof text === 'string' ? JSON.parse(text) : text, null, 2); } catch (e) { return String(text); }
}
async function openNode(id) {
  S.wf.node = id;
  $('#wf-layout').classList.remove('no-detail');
  $$('#wf-flow .node').forEach(n => n.classList.toggle('sel', n.dataset.id === id));
  drawEdges();
  const box = $('#wf-detail');
  box.innerHTML = `<div class="wf-detail-head"><h3>${t('wf.step')}</h3><button class="icon-btn" id="wf-detail-close">${icon('x')}</button></div><div class="empty">${icon('loader', 'spin')}</div>`;
  try {
    const s = await api(`/api/steps/${id}`);
    if (S.wf.node !== id) return;
    const step = S.wf.data?.steps.find(x => x.id === id) || s;
    const tasks = stepTasks(step);
    box.innerHTML = `<div class="wf-detail-head"><h3>${esc(toolTitle(s.tool))}</h3><span class="node-tool">${esc(s.tool)}</span>
        <button class="icon-btn" id="wf-detail-close">${icon('x')}</button></div>
      <div class="wf-detail-body">
        <div class="wf-meta" style="margin:0">${wfTag(s.status === 'error' ? 'failed' : s.status === 'running' ? 'active' : 'done')}<span>${ms(s.ms)}</span><span>${s.ts ? clock(s.ts) : ''}</span></div>
        <div><div class="label kv-label">${t('wf.args')}</div><pre class="json">${esc(prettyJson(s.args))}</pre></div>
        ${s.error ? `<div><div class="label kv-label">${t('wf.error')}</div><pre class="json" style="color:var(--err)">${esc(s.error)}</pre></div>` : ''}
        ${s.result ? `<div><div class="label kv-label">${t('wf.result')}</div><pre class="json">${esc(prettyJson(s.result))}</pre></div>` : ''}
        ${tasks.length ? `<div><div class="label kv-label">${t('wf.tasks')}</div>${tasks.map(tk => `<div class="sub-row">${kindIco(tk.file_kind || 'document')}<div class="sub-name">${esc(tk.title)}</div><div class="sub-prog">${taskTag(tk.status)}</div></div>`).join('')}</div>` : ''}
      </div>`;
  } catch (e) { box.innerHTML += `<div class="empty">${esc(e.message)}</div>`; }
}
function closeNode() {
  S.wf.node = null;
  $('#wf-layout').classList.add('no-detail');
  $$('#wf-flow .node').forEach(n => n.classList.remove('sel'));
  requestAnimationFrame(drawEdges);
}

/* ------------------------------------------------------------ log view */
function renderLog(main) {
  const items = [...S.activity.values()].sort((a, b) => b.id - a.id).slice(0, 200);
  main.innerHTML = `<div class="wf-head"><div class="wf-title">${t('wf.log')}</div></div>
    <div class="wf-canvas" style="padding-left:22px">${items.length ? items.map(ev => {
      const cls = ev.state === 'running' ? 'running' : (ev.level || 'info');
      return `<div class="ev ${cls}"><div class="ev-time">${clock(ev.ts).slice(-8)}</div><div class="ev-rail"><span class="ev-dot"></span></div>
        <div class="ev-main"><div class="ev-top">${who(ev.source)}<span class="ev-title">${esc(ev.title)}</span>${ev.tool ? `<span class="ev-tool">${esc(ev.tool)}</span>` : ''}</div>
        ${ev.detail ? `<div class="ev-detail">${esc(ev.detail)}</div>` : ''}${ev.result ? `<div class="ev-result">${esc(ev.result)}</div>` : ''}</div></div>`;
    }).join('') : `<div class="empty">${t('log.empty')}</div>`}</div>`;
}

/* ------------------------------------------------------------ live updates */
function onWorkflowEvent(w) {
  const isNew = !S.workflows.has(w.id);
  S.workflows.set(w.id, { ...(S.workflows.get(w.id) || {}), ...w });
  if (S.page !== 'workflow') { renderTop(); return; }
  if (S.wf.follow && w.status === 'active' && S.wf.sel !== w.id && (isNew || !S.wf.sel || S.workflows.get(S.wf.sel)?.status !== 'active')) {
    selectWorkflow(w.id);
    return;
  }
  renderWfList();
  if (S.wf.sel === w.id && S.wf.data) { S.wf.data.workflow = { ...S.wf.data.workflow, ...w }; renderWfMain(); }
}
function onStepEvent(s) {
  if (S.wf.follow && S.page === 'workflow' && S.wf.sel !== s.workflow_id) {
    const w = S.workflows.get(s.workflow_id);
    if (w && w.status === 'active') { selectWorkflow(s.workflow_id); return; }
  }
  if (S.wf.sel !== s.workflow_id || !S.wf.data) return;
  const steps = S.wf.data.steps;
  const i = steps.findIndex(x => x.id === s.id);
  if (i >= 0) steps[i] = { ...steps[i], ...s }; else { steps.push(s); S.wf.newIds.add(s.id); }
  if (S.page === 'workflow' && S.wf.view === 'flows') renderFlow();
}
let flowTimer = null;
function onTaskForFlow(tk) {
  if (S.page !== 'workflow' || !S.wf.data || tk.workflow_id !== S.wf.sel) return;
  if (flowTimer) return;
  flowTimer = setTimeout(() => { flowTimer = null; renderFlow(); }, 400);
}

function bindWorkflow() {
  $('#wf-items').onclick = e => { const it = e.target.closest('.wf-item'); if (it) { S.wf.follow = false; $('#wf-follow').checked = false; selectWorkflow(it.dataset.id); } };
  $('#wf-q').oninput = e => { S.wf.q = e.target.value; renderWfList(); };
  $('#wf-follow').onchange = e => { S.wf.follow = e.target.checked; };
  $('#wf-view').onclick = e => {
    const v = e.target.dataset.v; if (!v) return;
    S.wf.view = v; $$('#wf-view button').forEach(b => b.classList.toggle('on', b === e.target));
    renderWfMain();
  };
  $('#wf-main').addEventListener('click', async e => {
    if (e.target.closest('[data-ap]')) return onApproval(e);
    if (e.target.closest('#wf-del')) {
      if (!confirmBox(t('wf.deleteConfirm'))) return;
      await api(`/api/workflows/${S.wf.sel}`, { method: 'DELETE' });
      S.workflows.delete(S.wf.sel); S.wf.sel = null; S.wf.data = null; closeNode(); renderWfList(); renderWfMain();
      return;
    }
    const n = e.target.closest('.node');
    if (n) openNode(n.dataset.id);
  });
  $('#wf-main').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'wf-title-text') { e.preventDefault(); e.target.blur(); } });
  $('#wf-main').addEventListener('focusout', async e => {
    if (e.target.id !== 'wf-title-text') return;
    const title = e.target.textContent.trim();
    if (!title || title === S.wf.data?.workflow.title) return;
    await api(`/api/workflows/${S.wf.sel}`, { method: 'PATCH', body: { title } });
    S.wf.data.workflow.title = title;
    S.workflows.set(S.wf.sel, { ...S.workflows.get(S.wf.sel), title });
    renderWfList();
  });
  $('#wf-detail').addEventListener('click', e => { if (e.target.closest('#wf-detail-close')) closeNode(); });
  $('#approvals').onclick = onApproval;
  $('#approvals-2').onclick = onApproval;
  window.addEventListener('resize', () => requestAnimationFrame(drawEdges));
}
