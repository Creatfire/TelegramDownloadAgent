'use strict';
/* v1.2 pages and dialogs: dashboard, recipes, notes, file context, extraction, per-AI limits. */

Object.assign(ICONS, {
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19a2 2 0 0 1 2-2h13"/>',
  message: '<path d="M4 5h16v11H8l-4 4z"/>',
  ask: '<path d="M4 5h16v11H8l-4 4z"/><path d="M10 9a2 2 0 1 1 3 1.7c-.6.4-1 .8-1 1.5M12 14.5v.01"/>',
  note: '<path d="M5 4h10l4 4v12H5z"/><path d="M15 4v4h4M8 12h8M8 16h5"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M15 8l2 2"/>',
  box: '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/>',
});

Object.assign(I18N.zh, {
  'brand.sub': '给 AI 用的 Telegram 工作台', 'page.dashboard': '数据看板', 'page.recipes': '配方', 'tasks.jobs': '其他任务',
  'wf.st.wait': '等待', 'wf.st.run': '进行中', 'wf.st.done': '已完成', 'wf.st.err': '出错', 'wf.st.runNow': '进行中…',
  'wf.st.waitNow': '等待中…', 'wf.st.answer': '等你回答', 'wf.st.approve': '等你批准', 'wf.lane.general': '通用',
  'wf.lane.src': '资料', 'wf.lane.dl': '下载', 'wf.saveRecipe': '存为配方', 'wf.tech': '技术细节', 'wf.rawResult': '原始结果',
  'q.title': '{agent} 想问你', 'q.answer': '回答', 'q.dismiss': '忽略', 'q.placeholder': '输入你的回答', 'q.sent': '已回答', 'n.question': 'AI 在等你回答',
  'dash.d1': '24 小时', 'dash.d7': '7 天', 'dash.d30': '30 天', 'dash.refresh': '刷新', 'dash.noData': '还没有数据',
  'dash.k.today': '今日下载', 'dash.k.files': '{n} 个文件', 'dash.k.avg': '平均速度', 'dash.k.req': '今日 Telegram 请求', 'dash.k.floods': '限流 {n} 次',
  'dash.k.lib': '文件库', 'dash.k.arch': '消息存档', 'dash.k.msgs': '条消息', 'dash.k.wf': '进行中的工作流',
  'dash.speed': '下载速度（近 24 小时）', 'dash.daily': '每日下载量', 'dash.lib': '文件库构成', 'dash.byChat': '下载量最多的频道',
  'dash.scatter': '工具调用耗时', 'dash.agents': '各 AI 的调用次数', 'dash.requests': 'Telegram 请求（每小时）', 'dash.ok': '成功', 'dash.err': '出错',
  'dash.floods': '限流', 'dash.reqs': '请求',
  'lib.modeFiles': '文件', 'lib.modeMsgs': '消息', 'lib.msgPh': '在消息存档中搜索（标题、版本号、密码…）', 'lib.msgEmpty': '消息存档为空。浏览频道或为频道建立索引后，消息会自动存档。',
  'rec.title': '配方', 'rec.intro': '配方是可以重复使用的工作流。在 Claude Code 等客户端中，它们会显示为斜杠命令；也可以在这里直接运行或定时运行。任何工作流都能在工作流页“存为配方”。',
  'rec.run': '运行', 'rec.schedule': '定时', 'rec.builtin': '内置', 'rec.lastRun': '上次运行', 'rec.never': '从未', 'rec.params': '参数',
  'rec.started': '配方已开始运行', 'rec.delete': '删除', 'rec.deleteConfirm': '删除这个配方？', 'rec.none': '不定时', 'rec.every': '每隔几小时',
  'rec.daily': '每天固定时间', 'rec.hours': '间隔（小时）', 'rec.at': '时间', 'rec.schedSaved': '定时已保存', 'rec.saved': '已存为配方',
  'rec.nameAsk': '配方名称', 'rec.runs': '运行 {n} 次', 'rec.sched.every': '每 {n} 小时', 'rec.sched.daily': '每天 {t}',
  'note.button': '笔记', 'note.title': '频道笔记', 'note.desc': '所有 AI 都能读到这段笔记，例如命名规律、密码通常在哪条消息、文件在哪个频道。', 'note.saved': '笔记已保存',
  'ctx.button': '说明', 'ctx.title': '文件说明', 'ctx.passwords': '密码', 'ctx.versions': '版本', 'ctx.links': '链接', 'ctx.sizes': '大小', 'ctx.caption': '说明文字',
  'ctx.nearby': '附近的消息', 'ctx.none': '没有找到密码或版本信息', 'ctx.fromNearby': '来自附近消息',
  'ex.button': '解压', 'ex.title': '解压 / 校验', 'ex.password': '密码（没有可留空）', 'ex.test': '只校验，不解压', 'ex.start': '开始', 'ex.started': '已开始',
  'set.sevenzip': '7-Zip 路径', 'set.sevenzipPh': '留空则自动查找', 'set.dayReq': '每个 AI 每天的请求上限', 'set.dayGb': '每个 AI 每天的下载上限（GB）',
  'set.tgRpm': 'Telegram 请求上限 / 分钟', 'set.agents': '已接入的 AI', 'set.ai': 'AI 额度与安全',
  'set.aiDesc': '0 表示不限制。超出下载额度的请求会转为等你批准；可以为每个 AI 单独设置、限定频道或停用。',
  'act.extract': '解压', 'set.speedLimit': '限速（KB/s，0 为不限）', 'agent.name': 'AI', 'agent.today': '今日', 'agent.req': '请求/天', 'agent.gb': 'GB/天', 'agent.chats': '只允许的频道', 'agent.on': '启用', 'agent.saved': '已保存', 'agent.none': '还没有 AI 接入过',
});
Object.assign(I18N.en, {
  'brand.sub': 'Telegram workbench for AI', 'page.dashboard': 'Dashboard', 'page.recipes': 'Recipes', 'tasks.jobs': 'Other jobs',
  'wf.st.wait': 'Waiting', 'wf.st.run': 'Running', 'wf.st.done': 'Done', 'wf.st.err': 'Error', 'wf.st.runNow': 'Running…',
  'wf.st.waitNow': 'Waiting…', 'wf.st.answer': 'Needs your answer', 'wf.st.approve': 'Needs your approval', 'wf.lane.general': 'General',
  'wf.lane.src': 'source', 'wf.lane.dl': 'downloads', 'wf.saveRecipe': 'Save as recipe', 'wf.tech': 'Technical details', 'wf.rawResult': 'Raw result',
  'q.title': '{agent} has a question', 'q.answer': 'Answer', 'q.dismiss': 'Dismiss', 'q.placeholder': 'Type your answer', 'q.sent': 'Answered', 'n.question': 'The AI is waiting for your answer',
  'dash.d1': '24 h', 'dash.d7': '7 days', 'dash.d30': '30 days', 'dash.refresh': 'Refresh', 'dash.noData': 'No data yet',
  'dash.k.today': 'Downloaded today', 'dash.k.files': '{n} files', 'dash.k.avg': 'Average speed', 'dash.k.req': 'Telegram requests today', 'dash.k.floods': '{n} rate limits',
  'dash.k.lib': 'Library', 'dash.k.arch': 'Message archive', 'dash.k.msgs': 'messages', 'dash.k.wf': 'Active workflows',
  'dash.speed': 'Download speed (24 h)', 'dash.daily': 'Downloaded per day', 'dash.lib': 'Library by kind', 'dash.byChat': 'Top chats by download',
  'dash.scatter': 'Tool call duration', 'dash.agents': 'Calls per AI', 'dash.requests': 'Telegram requests per hour', 'dash.ok': 'ok', 'dash.err': 'errors',
  'dash.floods': 'rate limits', 'dash.reqs': 'requests',
  'lib.modeFiles': 'Files', 'lib.modeMsgs': 'Messages', 'lib.msgPh': 'Search the message archive (titles, versions, passwords…)', 'lib.msgEmpty': 'The message archive is empty. Messages are archived as you browse or index chats.',
  'rec.title': 'Recipes', 'rec.intro': 'Recipes are reusable workflows. MCP clients such as Claude Code show them as slash commands; you can also run them here or on a schedule. Any workflow can be saved as a recipe from the Workflows page.',
  'rec.run': 'Run', 'rec.schedule': 'Schedule', 'rec.builtin': 'built-in', 'rec.lastRun': 'Last run', 'rec.never': 'never', 'rec.params': 'Parameters',
  'rec.started': 'Recipe started', 'rec.delete': 'Delete', 'rec.deleteConfirm': 'Delete this recipe?', 'rec.none': 'No schedule', 'rec.every': 'Every few hours',
  'rec.daily': 'Daily at a time', 'rec.hours': 'Interval (hours)', 'rec.at': 'Time', 'rec.schedSaved': 'Schedule saved', 'rec.saved': 'Saved as a recipe',
  'rec.nameAsk': 'Recipe name', 'rec.runs': '{n} runs', 'rec.sched.every': 'every {n} h', 'rec.sched.daily': 'daily at {t}',
  'note.button': 'Note', 'note.title': 'Chat note', 'note.desc': 'Every AI can read this note: naming patterns, where passwords are posted, which chat holds the files…', 'note.saved': 'Note saved',
  'ctx.button': 'Details', 'ctx.title': 'File details', 'ctx.passwords': 'Passwords', 'ctx.versions': 'Versions', 'ctx.links': 'Links', 'ctx.sizes': 'Sizes', 'ctx.caption': 'Caption',
  'ctx.nearby': 'Nearby posts', 'ctx.none': 'No password or version found', 'ctx.fromNearby': 'from nearby posts',
  'ex.button': 'Extract', 'ex.title': 'Extract / test', 'ex.password': 'Password (leave empty if none)', 'ex.test': 'Only test, do not extract', 'ex.start': 'Start', 'ex.started': 'Started',
  'set.sevenzip': '7-Zip path', 'set.sevenzipPh': 'empty = auto-detect', 'set.dayReq': 'Requests per AI per day', 'set.dayGb': 'GB per AI per day',
  'set.tgRpm': 'Telegram requests / minute', 'set.agents': 'Connected AIs', 'set.ai': 'AI limits and safety',
  'set.aiDesc': '0 = unlimited. Downloads over an AI\'s byte quota wait for your approval; each AI can get its own limits, a chat allow-list, or be switched off.',
  'act.extract': 'Extract', 'set.speedLimit': 'Speed limit (KB/s, 0 = none)', 'agent.name': 'AI', 'agent.today': 'Today', 'agent.req': 'Req/day', 'agent.gb': 'GB/day', 'agent.chats': 'Only these chats', 'agent.on': 'On', 'agent.saved': 'Saved', 'agent.none': 'No AI has connected yet',
});

/* ============================================================ dashboard */
let dashDays = 7;
async function initDashboard() {
  $('#dash-kpis').innerHTML = `<div class="empty">${icon('loader', 'spin')}</div>`;
  try { renderDashboard(await api(`/api/dashboard?days=${dashDays}`)); } catch (e) { toast(e.message, false); }
}
function renderDashboard(d) {
  const k = d.kpi, empty = t('dash.noData');
  const tile = (key, v, s = '') => `<div class="kpi"><div class="k">${t(key)}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
  $('#dash-kpis').innerHTML = tile('dash.k.today', size(k.downloaded_today), t('dash.k.files', { n: k.files_today }))
    + tile('dash.k.avg', size(k.avg_speed) + '/s')
    + tile('dash.k.req', k.tg_requests_today, k.floods_today ? t('dash.k.floods', { n: k.floods_today }) : '')
    + tile('dash.k.lib', size(k.library_bytes), t('dash.k.files', { n: k.library_files }))
    + tile('dash.k.arch', k.archived_messages.toLocaleString(), t('dash.k.msgs'))
    + tile('dash.k.wf', k.active_workflows);
  const card = (id, title, wide = false) => `<div class="card ${wide ? 'wide' : ''}"><div class="card-head"><h2>${t(title)}</h2></div><div class="chart" id="${id}"></div></div>`;
  $('#dash-grid').innerHTML = card('ch-speed', 'dash.speed', true) + card('ch-daily', 'dash.daily') + card('ch-lib', 'dash.lib')
    + card('ch-chat', 'dash.byChat') + card('ch-agents', 'dash.agents') + card('ch-scatter', 'dash.scatter', true) + card('ch-req', 'dash.requests', true);
  const hm = ts => new Date(ts * 1000).toLocaleTimeString(LANG === 'zh' ? 'zh-CN' : 'en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
  const md = ts => { const x = new Date(ts * 1000); return `${x.getMonth() + 1}/${x.getDate()}`; };
  Charts.line($('#ch-speed'), [{ name: t('dash.speed'), points: d.speed_24h.map(p => ({ x: p.t, y: p.v })) }],
    { fmtY: v => size(v) + '/s', fmtX: hm, empty });
  Charts.bars($('#ch-daily'), d.daily.map(x => ({ label: x.day, short: x.day.slice(5), value: x.bytes })), { fmt: size, empty });
  Charts.donut($('#ch-lib'), d.library.map(x => ({ label: t('kind.' + x.kind) !== 'kind.' + x.kind ? t('kind.' + x.kind) : x.kind, value: x.bytes })),
    { fmt: size, center: size(d.library.reduce((a, x) => a + x.bytes, 0)), empty });
  Charts.bars($('#ch-chat'), d.by_chat.map(x => ({ label: String(x.chat), value: x.bytes })), { horizontal: true, fmt: size, empty });
  const pal = Charts.palette();
  Charts.bars($('#ch-agents'), d.agents.map(x => ({ label: x.agent, short: x.agent.slice(0, 10), ok: x.calls - x.errors, err: x.errors, value: x.calls })),
    { stacked: [{ key: 'ok', name: t('dash.ok'), color: pal[0] }, { key: 'err', name: t('dash.err'), color: getComputedStyle(document.documentElement).getPropertyValue('--err').trim() }], empty });
  const tools = [...new Set(d.scatter.map(p => p.tool))];
  const colorOf = tool => pal[tools.indexOf(tool) % pal.length];
  Charts.scatter($('#ch-scatter'), d.scatter.map(p => ({ x: p.t, y: Math.max(1, p.ms), color: p.status === 'error' ? 'var(--err)' : colorOf(p.tool),
    label: `${toolTitle(p.tool)} · ${ms(p.ms)} · ${clock(p.t)}` })),
    { logY: true, fmtY: v => ms(Math.round(v)), fmtX: dashDays > 1 ? md : hm, groups: tools.slice(0, 6).map(tl => [toolTitle(tl), colorOf(tl)]), empty });
  Charts.bars($('#ch-req'), d.requests_24h.map(x => ({ label: hm(x.t), short: hm(x.t), req: x.requests - x.floods, fl: x.floods, value: x.requests })),
    { stacked: [{ key: 'req', name: t('dash.reqs'), color: pal[1] }, { key: 'fl', name: t('dash.floods'), color: pal[2] }], empty });
}
function bindDashboard() {
  $('#dash-days').onclick = e => { const v = e.target.dataset.d; if (!v) return; dashDays = Number(v); $$('#dash-days button').forEach(b => b.classList.toggle('on', b === e.target)); initDashboard(); };
  $('#dash-refresh').onclick = initDashboard;
  window.addEventListener('resize', () => { if (S.page === 'dashboard') initDashboard(); });
}

/* ============================================================ recipes */
async function initRecipes() {
  try { S.recipes = await api('/api/recipes'); } catch (e) { S.recipes = []; }
  renderRecipes();
}
function schedText(r) {
  const s = r.schedule;
  if (!s) return '';
  return s.every_hours ? t('rec.sched.every', { n: s.every_hours }) : s.daily_at ? t('rec.sched.daily', { t: s.daily_at }) : '';
}
function renderRecipes() {
  $('#r-grid').innerHTML = (S.recipes || []).map(r => `<div class="card recipe" data-id="${esc(r.id)}">
    <div class="acc-top"><span class="node-ico" style="color:var(--accent)">${icon('book')}</span><div style="flex:1;min-width:0">
      <div class="acc-name">${esc(r.title)} ${r.builtin ? `<span class="tag">${t('rec.builtin')}</span>` : ''}</div>
      <div class="small muted mono">/${esc('recipe_' + r.name)}</div></div>${schedText(r) ? `<span class="tag info">${icon('clock')}${esc(schedText(r))}</span>` : ''}</div>
    ${r.description ? `<div class="small" style="color:var(--text-2)">${esc(r.description)}</div>` : ''}
    <div class="recipe-steps">${r.steps.map((s, i) => `<span>${i + 1}. ${esc(describe({ tool: s.tool, args: {} }).title)}</span>`).join('')}</div>
    <div class="small muted">${t('rec.lastRun')}: ${r.last_run ? ago(r.last_run) : t('rec.never')} · ${t('rec.runs', { n: r.runs || 0 })}</div>
    <div class="btn-row"><button class="btn primary sm" data-r="run">${icon('play')}${t('rec.run')}</button>
      <button class="btn ghost sm" data-r="schedule">${icon('clock')}${t('rec.schedule')}</button>
      ${r.builtin ? '' : `<button class="btn ghost sm danger" data-r="delete">${icon('trash')}${t('rec.delete')}</button>`}</div></div>`).join('');
}
function paramFields(r, values = {}) {
  return r.params.map(p => `<label>${esc(p.name)}${p.required ? ' *' : ''}<input name="p_${esc(p.name)}" value="${esc(values[p.name] ?? p.default ?? '')}" placeholder="${esc(p.description || '')}" ${p.required ? 'required' : ''}></label>`).join('');
}
const readParams = (r, fd) => Object.fromEntries(r.params.map(p => [p.name, (fd.get('p_' + p.name) || '').trim()]));
function runRecipeModal(r) {
  openModal(`<h3>${esc(r.title)}</h3><p class="muted small">${esc(r.description || '')}</p><form>${paramFields(r)}
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('rec.run')}</button></div></form>`,
  async fd => {
    const res = await post(`/api/recipes/${r.id}/run`, { params: readParams(r, fd) });
    toast(t('rec.started'));
    S.wf.follow = true;
    location.hash = 'workflow';
    setTimeout(() => selectWorkflow(res.workflow_id), 400);
  });
}
function scheduleModal(r) {
  const s = r.schedule || {};
  const mode = s.every_hours ? 'every' : s.daily_at ? 'daily' : 'none';
  openModal(`<h3>${t('rec.schedule')} · ${esc(r.title)}</h3><form>
    <label>${t('rec.schedule')}<select name="mode"><option value="none" ${mode === 'none' ? 'selected' : ''}>${t('rec.none')}</option>
      <option value="every" ${mode === 'every' ? 'selected' : ''}>${t('rec.every')}</option><option value="daily" ${mode === 'daily' ? 'selected' : ''}>${t('rec.daily')}</option></select></label>
    <div class="row-2"><label>${t('rec.hours')}<input name="hours" type="number" min="1" value="${esc(s.every_hours || 24)}"></label>
      <label>${t('rec.at')}<input name="at" type="time" value="${esc(s.daily_at || '03:00')}"></label></div>
    ${r.params.length ? `<div class="label">${t('rec.params')}</div>${paramFields(r, r.schedule_params || {})}` : ''}
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('set.save')}</button></div></form>`,
  async fd => {
    const m = fd.get('mode');
    const schedule = m === 'every' ? { every_hours: Number(fd.get('hours') || 24) } : m === 'daily' ? { daily_at: fd.get('at') } : null;
    await api(`/api/recipes/${r.id}`, { method: 'PATCH', body: { schedule, schedule_params: readParams(r, fd) } });
    toast(t('rec.schedSaved'));
    initRecipes();
  });
}
function saveRecipeModal() {
  const w = S.wf.data?.workflow;
  if (!w) return;
  openModal(`<h3>${t('wf.saveRecipe')}</h3><form><label>${t('rec.nameAsk')}<input name="title" value="${esc(w.explicit ? w.title : '')}" required></label>
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('set.save')}</button></div></form>`,
  async fd => { await post(`/api/workflows/${w.id}/save_recipe`, { title: fd.get('title') }); toast(t('rec.saved')); });
}
function bindRecipes() {
  $('#r-grid').onclick = async e => {
    const b = e.target.closest('[data-r]'); if (!b) return;
    const r = S.recipes.find(x => x.id === b.closest('.recipe').dataset.id);
    if (b.dataset.r === 'run') return runRecipeModal(r);
    if (b.dataset.r === 'schedule') return scheduleModal(r);
    if (b.dataset.r === 'delete' && confirmBox(t('rec.deleteConfirm'))) { await api(`/api/recipes/${r.id}`, { method: 'DELETE' }); initRecipes(); }
  };
}

/* ============================================================ notes, file context, extraction */
async function noteModal(account, chatId, chatTitle) {
  let current = '';
  try { const r = await tool('tg_notes', { account, action: 'get', chat: String(chatId) }); current = r.note || ''; } catch (e) { /* none */ }
  openModal(`<h3>${t('note.title')} · ${esc(chatTitle)}</h3><p class="muted small">${t('note.desc')}</p>
    <form><textarea name="text" rows="7">${esc(current)}</textarea>
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('set.save')}</button></div></form>`,
  async fd => {
    await post('/api/notes', { account, chat_id: chatId, chat_title: chatTitle, text: fd.get('text') });
    toast(t('note.saved'));
    if (S.b.info && String(S.b.info.id) === String(chatId)) { S.b.info.chat_note = fd.get('text'); renderChat(); }
  });
}
async function contextModal(account, chat, messageId) {
  openModal(`<h3>${t('ctx.title')}</h3><div class="empty">${icon('loader', 'spin')}</div>`);
  try {
    const r = await tool('tg_file_context', { account, chat: String(chat), message_id: Number(messageId) });
    const info = r.info || {}, near = r.info_from_nearby || {};
    const row = (k, own, nb, fmt = v => esc(v)) => {
      const a = own || [], b = (nb || []).filter(x => !a.includes(x));
      if (!a.length && !b.length) return '';
      return `<dt>${t(k)}</dt><dd>${a.map(fmt).join(' ')}${b.length ? ` <span class="muted small">${b.map(fmt).join(' ')} · ${t('ctx.fromNearby')}</span>` : ''}</dd>`;
    };
    const pw = v => `<span class="pw">${esc(v)}</span>`;
    const rows = row('ctx.passwords', info.passwords, near.passwords, pw) + row('ctx.versions', info.versions, near.versions)
      + row('ctx.sizes', info.sizes, near.sizes) + row('ctx.links', info.links, near.links, v => `<a href="${esc(v)}" target="_blank">${esc(v)}</a>`);
    $('#modal').innerHTML = `<h3>${esc(r.file?.name || t('ctx.title'))}</h3>
      <dl class="ctx-info">${rows || `<dt></dt><dd class="muted">${t('ctx.none')}</dd>`}</dl>
      ${r.caption ? `<div class="label" style="margin-top:14px">${t('ctx.caption')}</div><div class="msg-text">${esc(r.caption)}</div>` : ''}
      ${r.chat_note ? `<div class="label" style="margin-top:14px">${t('note.title')}</div><div class="chat-note" style="margin:6px 0 0">${esc(r.chat_note)}</div>` : ''}
      ${r.nearby?.length ? `<div class="label" style="margin-top:14px">${t('ctx.nearby')}</div>${r.nearby.filter(n => n.text).slice(0, 6).map(n => `<div class="msg"><div class="msg-head"><span>#${n.id}</span><span>${n.offset > 0 ? '+' : ''}${n.offset}</span></div><div class="msg-text">${esc(n.text)}</div></div>`).join('')}` : ''}
      <div class="modal-foot"><button class="btn" data-close>${t('common.close')}</button></div>`;
    $$('#modal [data-close]').forEach(b => b.onclick = closeModal);
  } catch (e) { $('#modal').innerHTML = `<div class="empty" style="color:var(--err)">${esc(e.message)}</div><div class="modal-foot"><button class="btn" data-close>${t('common.close')}</button></div>`; $$('#modal [data-close]').forEach(b => b.onclick = closeModal); }
}
function extractModal(taskIds) {
  openModal(`<h3>${t('ex.title')}</h3><form><label>${t('ex.password')}<input name="password" autocomplete="off"></label>
    <label class="check"><input type="checkbox" name="test">${t('ex.test')}</label>
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('ex.start')}</button></div></form>`,
  async fd => { await post('/api/tasks/extract', { task_ids: taskIds, password: fd.get('password') || null, test_only: !!fd.get('test') }); toast(t('ex.started')); });
}
const ARCHIVE_RE = /\.(7z|zip|rar|tar|gz|tgz|xz|bz2)(\.\d{2,4})?$|\.part\d+\.rar$|\.\d{3}$/i;

/* ============================================================ per-AI limits */
async function renderAgentTable() {
  const box = $('#agent-table');
  let agents = [];
  try { agents = await api('/api/agents'); } catch (e) { /* ignore */ }
  if (!agents.length) { box.innerHTML = `<div class="muted small">${t('agent.none')}</div>`; return; }
  box.innerHTML = `<table class="agent-table"><thead><tr><th>${t('agent.name')}</th><th>${t('agent.today')}</th><th>${t('agent.req')}</th><th>${t('agent.gb')}</th><th>${t('agent.chats')}</th><th>${t('agent.on')}</th><th></th></tr></thead><tbody>
    ${agents.map(a => `<tr data-agent="${esc(a.agent)}"><td>${who(a.agent)}</td><td class="small muted">${a.today.requests} · ${size(a.today.bytes)}</td>
      <td><input name="daily_requests" type="number" min="0" value="${a.limits.daily_requests}"></td>
      <td><input name="daily_gb" type="number" min="0" step="0.5" value="${a.limits.daily_gb}"></td>
      <td><input name="chats" value="${esc(a.limits.chats.join(', '))}" placeholder="@channel, …"></td>
      <td><input type="checkbox" name="on" ${a.limits.blocked ? '' : 'checked'}></td>
      <td><button type="button" class="btn sm" data-agent-save>${t('set.save')}</button></td></tr>`).join('')}</tbody></table>`;
}
function bindAgentTable() {
  $('#agent-table').addEventListener('click', async e => {
    if (!e.target.closest('[data-agent-save]')) return;
    const tr = e.target.closest('tr'), get = n => tr.querySelector(`[name=${n}]`);
    await post(`/api/agents/${encodeURIComponent(tr.dataset.agent)}/limits`, {
      daily_requests: Number(get('daily_requests').value || 0), daily_gb: Number(get('daily_gb').value || 0),
      chats: get('chats').value.split(/[,\s]+/).filter(Boolean), blocked: !get('on').checked });
    toast(t('agent.saved'));
  });
}
