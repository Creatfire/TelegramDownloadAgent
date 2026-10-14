'use strict';
/* Workflows page: list, swim-lane graph (one lane per chat), plain-language steps, details, approvals and questions. */

const WAIT_TOOLS = new Set(['tg_ask_user', 'tg_wait_tasks']);
const TOOL_ICON = {
  tg_resolve_chat: 'info', tg_get_messages: 'message', tg_search_messages: 'search', tg_get_message: 'message',
  tg_list_files: 'file', tg_list_dialogs: 'compass', tg_plan_download: 'scale', tg_download: 'download',
  tg_wait_tasks: 'clock', tg_index_chat: 'database', tg_search_files: 'search', tg_search_archive: 'search',
  tg_compare_chats: 'scale', tg_match_posts: 'link', tg_file_context: 'key', tg_ask_user: 'ask', tg_notes: 'note',
  tg_run_recipe: 'book', tg_list_recipes: 'book', tg_extract: 'box', tg_export: 'export', tg_watch: 'eye',
  tg_task_control: 'pause', tg_tasks: 'clock', tg_list_accounts: 'user', tg_index_status: 'database',
};

function q(s) { return s ? `“${String(s).slice(0, 40)}”` : ''; }
function describe(s) {
  const a = s.args || {}, zh = LANG === 'zh';
  const kinds = a.types ? (Array.isArray(a.types) ? a.types : [a.types]).map(k => t('kind.' + k)).join('/') : '';
  const T = {
    tg_resolve_chat: zh ? '查看频道信息' : 'Look up the chat',
    tg_list_dialogs: zh ? '列出已加入的对话' : 'List joined chats',
    tg_get_messages: a.query ? (zh ? `在消息里搜索${q(a.query)}` : `Search messages for ${q(a.query)}`) : (zh ? `读取 ${a.limit || 30} 条消息` : `Read ${a.limit || 30} messages`),
    tg_search_messages: zh ? `搜索${q(a.query)}` : `Search ${q(a.query)}`,
    tg_get_message: zh ? `读取消息 #${a.message_id || ''}` : `Read message #${a.message_id || ''}`,
    tg_list_files: zh ? `列出${kinds || ''}文件${a.name_contains ? '：' + q(a.name_contains) : ''}` : `List ${kinds || ''} files${a.name_contains ? ' ' + q(a.name_contains) : ''}`,
    tg_plan_download: zh ? '预估下载量' : 'Estimate the download',
    tg_download: zh ? `下载 ${a.message_ids ? a.message_ids.length + ' 个' : (a.links ? a.links.length + ' 个' : '')}文件` : `Download ${a.message_ids ? a.message_ids.length + ' ' : ''}files`,
    tg_wait_tasks: zh ? '等待任务完成' : 'Wait for tasks',
    tg_index_chat: zh ? '为频道建立索引' : 'Index the chat',
    tg_search_files: zh ? `在本地文件库搜索${q(a.query)}` : `Search the library ${q(a.query)}`,
    tg_search_archive: zh ? `在消息存档搜索${q(a.query)}` : `Search the archive ${q(a.query)}`,
    tg_compare_chats: zh ? '对比两个频道' : 'Compare two chats',
    tg_match_posts: zh ? '把介绍帖与文件配对' : 'Match intro posts to files',
    tg_file_context: zh ? '查看文件说明（密码 / 版本）' : 'Read file details (password / version)',
    tg_ask_user: zh ? '向你提问' : 'Ask you',
    tg_notes: zh ? (a.action === 'get' || a.action === 'list' ? '读取频道笔记' : '记录频道笔记') : (a.action === 'get' || a.action === 'list' ? 'Read notes' : 'Write a note'),
    tg_run_recipe: zh ? `运行配方 ${a.name || ''}` : `Run recipe ${a.name || ''}`,
    tg_list_recipes: zh ? '查看配方' : 'List recipes',
    tg_extract: a.test_only ? (zh ? '校验压缩包' : 'Test archives') : (zh ? '解压文件' : 'Extract archives'),
    tg_export: zh ? '导出清单' : 'Export a list',
    tg_watch: zh ? '管理订阅' : 'Manage watches',
    tg_task_control: zh ? `${a.action || ''} 任务` : `${a.action || ''} tasks`,
  };
  return { icon: TOOL_ICON[s.tool] || 'flow', title: (T[s.tool] || toolTitle(s.tool)).replace(/\s+/g, ' ').trim() };
}

function stepTasks(step) {
  const ids = new Set(step.task_ids || []);
  return [...S.tasks.values()].filter(tk => tk.step_id === step.id || ids.has(tk.id));
}
function stepState(s) {
  const tasks = stepTasks(s);
  if (s.status === 'error') return 'error';
  if (tasks.some(tk => tk.status === 'approval')) return 'wait';
  if (s.status === 'running') return WAIT_TOOLS.has(s.tool) ? 'wait' : 'run';
  if (tasks.some(tk => tk.status === 'running' || tk.status === 'queued')) return 'run';
  return 'done';
}
const questionFor = s => (S.questions || []).find(qq => qq.step_id === s.id && qq.status === 'open');

/* ------------------------------------------------------------ banners: approvals + questions */
function renderApprovals() {
  const qs = (S.questions || []).filter(qq => qq.status === 'open');
  const html = qs.map(qq => `<div class="approval question">${icon('ask')}
      <div class="ap-main"><div class="ap-title">${esc(t('q.title', { agent: qq.agent }))}</div><div>${esc(qq.question)}</div></div>
      ${answerControls(qq)}</div>`).join('')
    + S.approvals.map(a => `<div class="approval">${icon('shield')}
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
function answerControls(qq) {
  return `<div class="q-answers" data-q="${qq.id}">${(qq.options || []).map(o => `<button class="btn sm" data-answer="${esc(o)}">${esc(o)}</button>`).join('')}
    ${qq.allow_text ? `<input data-answer-text placeholder="${esc(t('q.placeholder'))}"><button class="btn sm primary" data-answer-send>${t('q.answer')}</button>` : ''}
    <button class="btn sm ghost" data-q-dismiss>${t('q.dismiss')}</button></div>`;
}
async function onApproval(e) {
  const qa = e.target.closest('[data-q]');
  if (qa && (e.target.closest('[data-answer]') || e.target.closest('[data-answer-send]') || e.target.closest('[data-q-dismiss]'))) {
    const id = qa.dataset.q;
    const btn = e.target.closest('[data-answer]');
    const body = e.target.closest('[data-q-dismiss]') ? { dismiss: true }
      : { answer: btn ? btn.dataset.answer : $('[data-answer-text]', qa).value.trim() };
    if (!body.dismiss && !body.answer) return;
    try { await post(`/api/questions/${id}`, body); toast(t('q.sent')); } catch (err) { toast(err.message, false); }
    return;
  }
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
  [S.approvals, S.watches, S.questions] = await Promise.all([api('/api/approvals'), api('/api/watches'), api('/api/questions')]);
  renderApprovals();
  if (S.page === 'workflow') renderFlow();
  render();
}

/* ------------------------------------------------------------ list */
function renderWfList() {
  const box = $('#wf-items');
  const qs = S.wf.q.toLowerCase();
  let items = [...S.workflows.values()].sort((a, b) => b.updated - a.updated);
  if (qs) items = items.filter(w => (w.title || '').toLowerCase().includes(qs) || (w.agent || '').toLowerCase().includes(qs));
  if (!items.length) { box.innerHTML = `<div class="empty">${t('wf.none')}</div>`; return; }
  const today = new Date().toDateString();
  const groups = [[t('wf.active'), items.filter(w => w.status === 'active')],
                  [t('wf.today'), items.filter(w => w.status !== 'active' && new Date(w.updated * 1000).toDateString() === today)],
                  [t('wf.earlier'), items.filter(w => w.status !== 'active' && new Date(w.updated * 1000).toDateString() !== today)]];
  box.innerHTML = groups.filter(g => g[1].length).map(([label, list]) => `<div class="wf-group">${label}</div>` + list.slice(0, 150).map(w => `
    <div class="wf-item ${S.wf.sel === w.id ? 'on' : ''}" data-id="${w.id}">
      <span class="st ${w.status}"></span>
      <div class="wf-item-title ${w.explicit ? '' : 'implicit'}">${esc(w.explicit ? w.title : t('wf.untitled'))}</div>
      <div class="wf-item-meta">${who(w.agent)}<span>${t('wf.steps', { n: w.steps })}</span><span>${ago(w.updated)}</span></div>
    </div>`).join('')).join('');
}

async function selectWorkflow(id) {
  if (S.wf.sel !== id) { S.wf.node = null; $('#wf-layout').classList.add('no-detail'); }
  S.wf.sel = id;
  renderWfList();
  try {
    const d = await api(`/api/workflows/${id}`);
    if (S.wf.sel !== id) return;
    S.wf.data = d;
    for (const tk of d.tasks || []) S.tasks.set(tk.id, tk);
    renderWfMain();
  } catch (e) { $('#wf-main').innerHTML = `<div class="empty big">${icon('alert')}<p>${esc(e.message)}</p></div>`; }
}

/* ------------------------------------------------------------ lanes model */
function laneModel(steps) {
  const lanes = [], index = {};
  const add = ln => { if (!(ln.key in index)) { index[ln.key] = lanes.length; lanes.push({ ...ln, tools: new Set() }); } return index[ln.key]; };
  const general = steps.some(s => !s.lanes || !s.lanes.length || s.lanes[0].key === 'general');
  steps.forEach(s => (s.lanes && s.lanes.length ? s.lanes : [{ key: 'general', title: '' }]).forEach(ln => { if (ln.key !== 'general') add(ln); }));
  if (general || !lanes.length) add({ key: 'general', title: '' });
  steps.forEach(s => {
    const ls = (s.lanes && s.lanes.length ? s.lanes : [{ key: 'general' }]);
    ls.forEach(ln => lanes[index[ln.key]]?.tools.add(s.tool));
  });
  lanes.forEach(ln => {
    ln.role = ln.key === 'general' ? '' : (['tg_download', 'tg_plan_download', 'tg_extract'].some(x => ln.tools.has(x)) ? 'dl'
      : ['tg_get_messages', 'tg_search_messages', 'tg_file_context', 'tg_search_archive'].some(x => ln.tools.has(x)) ? 'src' : '');
  });
  // rows: a step joins the previous row when it started before that row's steps finished and its columns are free
  const place = [];
  let row = 0, rowEnd = 0, used = new Set();
  steps.forEach((s, i) => {
    const cols = (s.lanes && s.lanes.length ? s.lanes : [{ key: 'general' }]).map(ln => index[ln.key] ?? index.general ?? 0);
    const c0 = Math.min(...cols), c1 = Math.max(...cols);
    const span = []; for (let c = c0; c <= c1; c++) span.push(c);
    const end = s.ts + (s.ms != null ? s.ms / 1000 : (s.status === 'running' ? 1e12 : 0));
    const parallel = i > 0 && s.ts < rowEnd - 0.05 && span.every(c => !used.has(c));
    if (!parallel) { row++; used = new Set(); rowEnd = 0; }
    span.forEach(c => used.add(c));
    rowEnd = Math.max(rowEnd, end);
    place.push({ row, c0, c1, parallel });
  });
  return { lanes, place };
}

/* ------------------------------------------------------------ main panel */
function story(w, steps) {
  const zh = LANG === 'zh';
  const { lanes } = laneModel(steps);
  const end = w.ended || (w.status === 'active' ? Date.now() / 1000 : w.updated);
  const parts = [];
  lanes.filter(l => l.key !== 'general').forEach(ln => {
    const ss = steps.filter(s => (s.lanes || []).some(x => x.key === ln.key));
    const cnt = k => ss.filter(s => k.includes(s.tool)).length;
    const acts = [];
    const reads = cnt(['tg_get_messages', 'tg_get_message', 'tg_search_messages']);
    if (reads) acts.push(zh ? `读了 ${reads} 次消息` : `read messages ${reads}×`);
    const lists = cnt(['tg_list_files', 'tg_index_chat', 'tg_search_files']);
    if (lists) acts.push(zh ? `查看文件 ${lists} 次` : `looked at files ${lists}×`);
    const dl = ss.filter(s => s.tool === 'tg_download').flatMap(stepTasks);
    if (dl.length) acts.push(zh ? `下载 ${dl.length} 个文件（${size(dl.reduce((x, tk) => x + tk.total, 0))}）` : `downloaded ${dl.length} files (${size(dl.reduce((x, tk) => x + tk.total, 0))})`);
    if (cnt(['tg_match_posts'])) acts.push(zh ? '与另一个频道配对' : 'matched against another chat');
    if (cnt(['tg_file_context'])) acts.push(zh ? '查看了文件说明' : 'checked file details');
    if (acts.length) parts.push(zh ? `在<b>「${esc(ln.title)}」</b>${acts.join('，')}` : `in <b>${esc(ln.title)}</b> ${acts.join(', ')}`);
  });
  const nCh = lanes.filter(l => l.key !== 'general').length;
  let text = zh ? `${who(w.agent)} 用时 ${dur(end - w.created)}${nCh > 1 ? `，在 <b>${nCh}</b> 个频道之间工作` : ''}。` : `${who(w.agent)} worked for ${dur(end - w.created)}${nCh > 1 ? ` across <b>${nCh}</b> chats` : ''}. `;
  if (parts.length) text += (zh ? parts.join('；') + '。' : parts.join('; ') + '.');
  const running = steps.filter(s => s.status === 'running');
  if (running.length) text += ' ' + (zh ? `现在：${esc(describe(running.at(-1)).title)}。` : `Now: ${esc(describe(running.at(-1)).title)}.`);
  const qs = (S.questions || []).filter(qq => qq.workflow_id === w.id && qq.status === 'open').length;
  if (qs) text += ' ' + (zh ? `<b>正在等你回答 ${qs} 个问题。</b>` : `<b>Waiting for your answer (${qs}).</b>`);
  return text;
}

function renderWfMain() {
  const main = $('#wf-main');
  if (S.wf.view === 'log') { renderLog(main); return; }
  const d = S.wf.data;
  if (!d) { main.innerHTML = `<div class="empty big">${icon('flow')}<p>${t(S.workflows.size ? 'wf.pick' : 'wf.none')}</p></div>`; return; }
  const w = { ...d.workflow, ...(S.workflows.get(d.workflow.id) || {}) };
  main.innerHTML = `
    <div class="wf-head">
      <div class="wf-title"><span ${w.explicit ? `contenteditable="plaintext-only" spellcheck="false" title="${esc(t('wf.renameHint'))}"` : ''} id="wf-title-text">${esc(w.explicit ? w.title : t('wf.untitled'))}</span>${wfTag(w.status)}
        <span class="wf-actions">
          <button class="btn ghost sm" id="wf-save-recipe">${icon('book')}${t('wf.saveRecipe')}</button>
          <button class="btn ghost sm" id="wf-report">${icon('report')}${t('wf.report')}</button>
          <button class="btn ghost sm" id="wf-rerun">${icon('retry')}${t('wf.rerun')}</button>
          <button class="icon-btn danger" id="wf-del" title="${t('wf.delete')}">${icon('trash')}</button></span></div>
      <div class="wf-story" id="wf-story"></div>
      ${w.goal ? `<div class="wf-story muted">${esc(w.goal)}</div>` : ''}
      ${w.summary ? `<div class="wf-summary">${esc(w.summary)}</div>` : ''}
      ${w.explicit ? '' : `<div class="wf-story muted small">${icon('info')} ${t('wf.implicitTip')}</div>`}
      <div class="wf-legend"><span><i class="sw sw-wait"></i>${t('wf.st.wait')}</span><span><i class="sw sw-run"></i>${t('wf.st.run')}</span>
        <span><i class="sw sw-done"></i>${t('wf.st.done')}</span><span><i class="sw sw-err"></i>${t('wf.st.err')}</span></div>
    </div>
    <div class="wf-canvas" id="wf-canvas"></div>`;
  renderFlow();
}

function nodeHtml(s, state) {
  const dsc = describe(s);
  const tasks = stepTasks(s), pending = tasks.filter(tk => tk.status === 'approval');
  const qq = questionFor(s);
  const badges = [];
  if (s.polls) badges.push(`<span class="tag">${t('wf.polls', { n: s.polls })}</span>`);
  let sub = '';
  if (tasks.length) {
    const shown = tasks.slice(0, 5);
    sub = `<div class="node-sub">${shown.map(tk => `
        <div class="sub-row">${kindIco(tk.kind === 'download' ? tk.file_kind : 'document')}<div class="sub-name" title="${esc(tk.title)}">${esc(tk.title)}</div>
          <div class="sub-prog">${waitText(tk) || (tk.status === 'running' && tk.kind === 'download' ? `${pct(tk).toFixed(0)}% · ${size(tk.speed)}/s` : t('task.' + tk.status))}
            <div class="bar ${tk.status}"><div style="width:${tk.kind === 'download' ? pct(tk) : (tk.status === 'done' ? 100 : tk.status === 'running' ? 50 : 0)}%"></div></div></div></div>`).join('')}
      ${tasks.length > shown.length ? `<div class="sub-more">${t('wf.more', { n: tasks.length - shown.length })}</div>` : ''}</div>`;
  }
  const stateLine = state === 'run' ? `<div class="node-state">${t('wf.st.runNow')}</div>`
    : state === 'wait' ? `<div class="node-state">${qq ? t('wf.st.answer') : pending.length ? t('wf.st.approve') : t('wf.st.waitNow')}</div>` : '';
  const ask = qq ? `<div class="node-ask"><div class="q">${esc(qq.question)}</div>${answerControls(qq)}</div>` : '';
  const approval = pending.length ? `<div class="node-approval"><span>${esc(t('ap.node', { n: pending.length, size: size(pending.reduce((x, tk) => x + tk.total, 0)) }))}</span>
      <button class="btn sm ghost" data-ap="${pending[0].batch}" data-ok="0">${t('ap.reject')}</button>
      <button class="btn sm primary" data-ap="${pending[0].batch}" data-ok="1">${t('ap.approve')}</button></div>` : '';
  return `<div class="node ${state} ${S.wf.node === s.id ? 'sel' : ''}" data-id="${s.id}">
    <div class="node-head"><span class="node-ico">${s.status === 'running' && state === 'run' ? icon('loader', 'spin') : icon(dsc.icon)}</span>
      <span class="node-title" title="${esc(dsc.title)}">${esc(dsc.title)}</span><span class="node-time">${clock(s.ts).slice(-8, -3)}</span></div>
    ${stateLine}
    ${s.status === 'error' ? `<div class="node-error">${esc(s.error)}</div>` : s.summary ? `<div class="node-result">${esc(s.summary)}</div>` : ''}
    <div class="node-badges">${badges.join('')}</div>${ask}${approval}${sub}</div>`;
}

function renderFlow() {
  const canvas = $('#wf-canvas');
  if (!canvas || !S.wf.data) return;
  const story_ = $('#wf-story');
  const w = { ...S.wf.data.workflow, ...(S.workflows.get(S.wf.data.workflow.id) || {}) };
  const steps = S.wf.data.steps;
  if (story_) story_.innerHTML = story(w, steps);
  const nearBottom = canvas.scrollHeight - canvas.scrollTop - canvas.clientHeight < 80;
  if (!steps.length) { canvas.innerHTML = `<div class="empty">${t('wf.noSteps')}</div>`; return; }
  const { lanes, place } = laneModel(steps);
  const cols = `repeat(${lanes.length}, minmax(${lanes.length > 2 ? 230 : 260}px, 1fr))`;
  const roleTag = r => r === 'dl' ? `<span class="tag info">${t('wf.lane.dl')}</span>` : r === 'src' ? `<span class="tag">${t('wf.lane.src')}</span>` : '';
  const head = lanes.length > 1 || lanes[0].key !== 'general'
    ? `<div class="lanes-head" style="grid-template-columns:${cols}">${lanes.map(ln => ln.key === 'general'
        ? `<div class="lane-h"><span class="avatar" style="--h:30">·</span><span class="t">${t('wf.lane.general')}</span></div>`
        : `<div class="lane-h">${avatar(ln.title)}<span class="t" title="${esc(ln.title)}">${esc(ln.title)}</span>${roleTag(ln.role)}</div>`).join('')}</div>` : '';
  const endCls = w.status === 'active' ? 'live' : w.status === 'failed' ? 'failed' : '';
  const endText = w.status === 'active' ? t('wf.waiting') : w.status === 'failed' ? t('wf.failedEnd') : w.status === 'done' ? t('wf.finished') : t('wf.idleEnd');
  canvas.innerHTML = head + `<div class="lanes" id="wf-lanes" style="grid-template-columns:${cols}"><svg class="edges" id="wf-edges"></svg>`
    + steps.map((s, i) => `<div style="grid-row:${place[i].row};grid-column:${place[i].c0 + 1} / ${place[i].c1 + 2};min-width:0">${nodeHtml(s, stepState(s))}</div>`).join('')
    + `</div><div class="flow-end ${endCls}"><span class="dot"></span>${endText}</div>`;
  requestAnimationFrame(() => { drawEdges(); if (S.wf.follow && nearBottom) canvas.scrollTop = canvas.scrollHeight; });
}

function drawEdges() {
  const box = $('#wf-lanes'), svg = $('#wf-edges');
  if (!box || !svg || !S.wf.data) return;
  const nodes = {};
  $$('#wf-lanes .node').forEach(el => { nodes[el.dataset.id] = el; });
  svg.setAttribute('width', box.scrollWidth);
  svg.setAttribute('height', box.scrollHeight);
  const steps = S.wf.data.steps, laneOf = {};
  steps.forEach(s => { laneOf[s.id] = (s.lanes && s.lanes[0] ? s.lanes[0].key : 'general'); });
  const sel = S.wf.node, base = box.getBoundingClientRect();
  const parts = [];
  steps.forEach(s => {
    const ce = nodes[s.id];
    if (!ce) return;
    const cr = ce.getBoundingClientRect();
    for (const p of s.parents || []) {
      const pe = nodes[p.id];
      if (!pe) continue;
      const pr = pe.getBoundingClientRect();
      const x1 = pr.left - base.left + pr.width / 2, y1 = pr.bottom - base.top;
      const x2 = cr.left - base.left + cr.width / 2, y2 = cr.top - base.top;
      const crossLane = laneOf[p.id] !== laneOf[s.id];
      const cls = 'edge ' + (p.kind === 'data' ? (crossLane ? 'cross' : 'data') : '') + (sel && (sel === s.id || sel === p.id) ? ' hl' : '');
      const dy = Math.max(18, (y2 - y1) / 2);
      parts.push(Math.abs(x1 - x2) < 2 ? `<path class="${cls}" d="M${x1},${y1} V${y2}"/>`
        : `<path class="${cls}" d="M${x1},${y1} C${x1},${y1 + dy} ${x2},${y2 - dy} ${x2},${y2}"/>`);
    }
  });
  svg.innerHTML = parts.join('');
}

/* ------------------------------------------------------------ details */
function prettyJson(text) {
  if (text == null || text === '') return '';
  try { return JSON.stringify(typeof text === 'string' ? JSON.parse(text) : text, null, 2); } catch (e) { return String(text); }
}
async function openNode(id) {
  S.wf.node = id;
  $('#wf-layout').classList.remove('no-detail');
  $$('#wf-lanes .node').forEach(n => n.classList.toggle('sel', n.dataset.id === id));
  requestAnimationFrame(drawEdges);
  const box = $('#wf-detail');
  box.innerHTML = `<div class="wf-detail-head"><h3>${t('wf.step')}</h3><button class="icon-btn" id="wf-detail-close">${icon('x')}</button></div><div class="empty">${icon('loader', 'spin')}</div>`;
  try {
    const s = await api(`/api/steps/${id}`);
    if (S.wf.node !== id) return;
    const step = S.wf.data?.steps.find(x => x.id === id) || s;
    const tasks = stepTasks(step), dsc = describe(step);
    box.innerHTML = `<div class="wf-detail-head"><h3>${esc(dsc.title)}</h3><button class="icon-btn" id="wf-detail-close">${icon('x')}</button></div>
      <div class="wf-detail-body">
        <div class="wf-meta muted small">${(step.lanes || []).filter(l => l.key !== 'general').map(l => esc(l.title)).join(' ⇄ ')} ${ms(s.ms) ? '· ' + ms(s.ms) : ''} · ${s.ts ? clock(s.ts) : ''}</div>
        ${step.summary ? `<div><div class="label kv-label">${t('wf.result')}</div><div>${esc(step.summary)}</div></div>` : ''}
        ${s.error ? `<div><div class="label kv-label">${t('wf.error')}</div><pre class="json" style="color:var(--err)">${esc(s.error)}</pre></div>` : ''}
        ${tasks.length ? `<div><div class="label kv-label">${t('wf.tasks')}</div>${tasks.map(tk => `<div class="sub-row">${kindIco(tk.file_kind || 'document')}<div class="sub-name">${esc(tk.title)}</div><div class="sub-prog">${taskTag(tk.status)}</div></div>`).join('')}</div>` : ''}
        <div><div class="label kv-label">${t('wf.tech')} · <span class="mono">${esc(s.tool)}</span></div><pre class="json">${esc(prettyJson(s.args))}</pre></div>
        ${s.result ? `<div><div class="label kv-label">${t('wf.rawResult')}</div><pre class="json">${esc(prettyJson(s.result))}</pre></div>` : ''}
      </div>`;
  } catch (e) { box.innerHTML += `<div class="empty">${esc(e.message)}</div>`; }
}
function closeNode() {
  S.wf.node = null;
  $('#wf-layout').classList.add('no-detail');
  $$('#wf-lanes .node').forEach(n => n.classList.remove('sel'));
  requestAnimationFrame(drawEdges);
}

/* ------------------------------------------------------------ log view */
function renderLog(main) {
  const items = [...S.activity.values()].sort((a, b) => b.id - a.id).slice(0, 200);
  main.innerHTML = `<div class="wf-head"><div class="wf-title">${t('wf.log')}</div></div>
    <div class="wf-canvas" style="padding-top:8px">${items.length ? items.map(ev => `<div class="ev ${ev.level || ''}"><div class="ev-time">${clock(ev.ts).slice(-8)}</div>
      <div><div class="ev-top">${who(ev.source)}<span class="ev-title">${esc(ev.title)}</span>${ev.tool ? `<span class="ev-tool">${esc(ev.tool)}</span>` : ''}</div>
      ${ev.detail ? `<div class="ev-detail">${esc(ev.detail)}</div>` : ''}${ev.result ? `<div class="ev-result">${esc(ev.result)}</div>` : ''}</div></div>`).join('')
      : `<div class="empty">${t('log.empty')}</div>`}</div>`;
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
  if (S.wf.sel === w.id && S.wf.data) { S.wf.data.workflow = { ...S.wf.data.workflow, ...w }; renderFlow(); }
}
function onStepEvent(s) {
  if (S.wf.follow && S.page === 'workflow' && S.wf.sel !== s.workflow_id) {
    const w = S.workflows.get(s.workflow_id);
    if (w && w.status === 'active') { selectWorkflow(s.workflow_id); return; }
  }
  if (S.wf.sel !== s.workflow_id || !S.wf.data) return;
  const steps = S.wf.data.steps;
  const i = steps.findIndex(x => x.id === s.id);
  if (i >= 0) steps[i] = { ...steps[i], ...s }; else steps.push(s);
  if (S.page === 'workflow' && S.wf.view === 'flows') renderFlow();
}
let flowTimer = null;
function onTaskForFlow(tk) {
  if (S.page !== 'workflow' || !S.wf.data || tk.workflow_id !== S.wf.sel) return;
  if (flowTimer) return;
  flowTimer = setTimeout(() => { flowTimer = null; renderFlow(); }, 500);
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
    if (e.target.closest('[data-ap],[data-q]')) return onApproval(e);
    if (e.target.closest('#wf-report')) {
      const r = await fetch(`/api/workflows/${S.wf.sel}/report`, { credentials: 'same-origin' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([await r.text()], { type: 'text/markdown' }));
      a.download = `workflow-${S.wf.sel}.md`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      return;
    }
    if (e.target.closest('#wf-save-recipe')) return saveRecipeModal();
    if (e.target.closest('#wf-rerun')) {
      if (!confirmBox(t('wf.rerunConfirm'))) return;
      try { const r = await post(`/api/workflows/${S.wf.sel}/rerun`); toast(t('wf.rerunStarted')); S.wf.follow = true; $('#wf-follow').checked = true; setTimeout(() => selectWorkflow(r.workflow_id), 300); }
      catch (err) { toast(err.message, false); }
      return;
    }
    if (e.target.closest('#wf-del')) {
      if (!confirmBox(t('wf.deleteConfirm'))) return;
      await api(`/api/workflows/${S.wf.sel}`, { method: 'DELETE' });
      S.workflows.delete(S.wf.sel); S.wf.sel = null; S.wf.data = null; closeNode(); renderWfList(); renderWfMain();
      return;
    }
    if (e.target.closest('input,button')) return;
    const n = e.target.closest('.node');
    if (n) openNode(n.dataset.id);
  });
  $('#wf-main').addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.id === 'wf-title-text') { e.preventDefault(); e.target.blur(); }
    if (e.key === 'Enter' && e.target.matches('[data-answer-text]')) e.target.closest('[data-q]').querySelector('[data-answer-send]').click();
  });
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
  for (const id of ['#approvals', '#approvals-2']) $(id).addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.matches('[data-answer-text]')) e.target.closest('[data-q]').querySelector('[data-answer-send]').click();
  });
  window.addEventListener('resize', () => requestAnimationFrame(drawEdges));
}
