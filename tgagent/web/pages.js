'use strict';
/* Browse, Library, Tasks, Watches, Accounts, Connect and Settings pages. */

/* ============================================================ browse */
let browseInited = false;
function readyAccounts() { return S.accounts.filter(a => a.status === 'ready'); }
function accountOptions(selected, onlyReady = true) {
  return S.accounts.map(a => `<option value="${esc(a.id)}" ${a.id === selected ? 'selected' : ''} ${onlyReady && a.status !== 'ready' ? 'disabled' : ''}>${esc(a.name)}${a.me?.username ? ' (@' + esc(a.me.username) + ')' : ''}</option>`).join('');
}
function initBrowse() {
  const ready = readyAccounts();
  if (!S.b.account || !ready.find(a => a.id === S.b.account)) S.b.account = (ready.find(a => a.is_default) || ready[0])?.id || '';
  $('#b-account').innerHTML = accountOptions(S.b.account) || `<option value="">${t('acc.none')}</option>`;
  if (!S.b.chat) $('#b-chat').innerHTML = `<div class="empty big">${icon('compass')}<p>${t('browse.pick')}</p></div>`;
  if (!browseInited && S.b.account) { browseInited = true; loadDialogs(); }
  else if (!S.b.account) $('#b-dialogs').innerHTML = `<div class="empty">${t('browse.noAccount')}</div>`;
  else renderDialogs();
}
async function loadDialogs() {
  if (!S.b.account) return;
  $('#b-dialogs').innerHTML = `<div class="empty">${icon('loader', 'spin')} ${t('browse.loading')}</div>`;
  try {
    const r = await tool('tg_list_dialogs', { account: S.b.account, kind: S.b.kind, query: S.b.q, limit: 300 });
    S.b.dialogs = r.dialogs;
    renderDialogs();
  } catch (e) { $('#b-dialogs').innerHTML = `<div class="empty" style="color:var(--err)">${esc(e.message)}</div>`; }
}
function renderDialogs() {
  if (!S.b.dialogs.length) { $('#b-dialogs').innerHTML = `<div class="empty">${t('browse.none')}</div>`; return; }
  $('#b-dialogs').innerHTML = S.b.dialogs.map(d => `<div class="dialog ${S.b.chat == d.id ? 'on' : ''}" data-id="${d.id}">
    ${avatar(d.title)}<div class="dialog-main"><div class="dialog-title">${esc(d.title)}</div>
    <div class="dialog-sub">${t('type.' + d.type)}${d.username ? ' · @' + esc(d.username) : ' · ' + t('browse.private')}${d.members ? ' · ' + d.members : ''}</div></div>
    ${d.unread ? `<span class="unread">${d.unread > 999 ? '999+' : d.unread}</span>` : ''}</div>`).join('');
}
async function openChat(ref) {
  const b = S.b;
  Object.assign(b, { chat: ref, info: null, files: [], fileCursor: null, fileSummary: null, msgs: [], msgCursor: null, selected: new Set() });
  renderDialogs();
  $('#b-chat').innerHTML = `<div class="empty big">${icon('loader', 'spin')}<p>${t('browse.loading')}</p></div>`;
  try {
    b.info = await tool('tg_resolve_chat', { account: b.account, chat: String(ref) });
    if (b.info.invite && !b.info.joined) { renderChat(); return; }
    b.chat = b.info.id;
    renderChat();
    await (b.tab === 'files' ? loadFiles() : loadMsgs());
  } catch (e) { $('#b-chat').innerHTML = `<div class="empty big" style="color:var(--err)">${icon('alert')}<p>${esc(e.message)}</p></div>`; }
}
function renderChat() {
  const b = S.b, i = b.info;
  if (!i) return;
  if (i.invite && !i.joined) {
    $('#b-chat').innerHTML = `<div class="chat-head">${avatar(i.title)}<div><div class="chat-title">${esc(i.title)}</div><div class="chat-about">${esc(i.about || '')}</div></div></div>
      <div class="empty big">${icon('info')}<p>${t('browse.notJoined')} · ${esc(i.note || '')}</p></div>`;
    return;
  }
  const chips = ['document', 'video', 'audio', 'photo', 'voice'].map(k => `<button class="chip ${b.f.types.includes(k) ? 'on' : ''}" data-type="${k}">${t('kind.' + k)}</button>`).join('');
  $('#b-chat').innerHTML = `
    <div class="chat-head">${avatar(i.title)}<div style="flex:1;min-width:0"><div class="chat-title">${esc(i.title)}</div>
      <div class="chat-meta">${t('type.' + i.type)} · ${i.username ? '@' + esc(i.username) : t('browse.private')}${i.members ? ' · ' + t('browse.members', { n: i.members }) : ''}${i.latest_message_id ? ' · ' + t('browse.latest', { n: i.latest_message_id }) : ''} · ${i.id}</div>
      ${i.about ? `<div class="chat-about">${esc(i.about)}</div>` : ''}</div>
      <div class="btn-row"><button class="btn sm" id="b-index">${icon('database')}${t('browse.index')}</button><button class="btn sm" id="b-export">${icon('export')}${t('browse.export')}</button>
        ${i.link ? `<a class="btn sm ghost" href="${esc(i.link)}" target="_blank">${icon('external')}${t('browse.openTg')}</a>` : ''}</div></div>
    <div class="chat-tabs">
      <div class="seg" id="b-tab"><button data-t="files" class="${b.tab === 'files' ? 'on' : ''}">${t('browse.files')}</button><button data-t="msgs" class="${b.tab === 'msgs' ? 'on' : ''}">${t('browse.msgs')}</button></div>
      ${b.tab === 'files' ? `<div class="filters">${chips}
        <input id="f-name" placeholder="${t('browse.nameHas')}" value="${esc(b.f.name)}"><input id="f-ext" class="short" placeholder="${t('browse.ext')}" value="${esc(b.f.ext)}">
        <input id="f-min" class="short" type="number" placeholder="≥ MB" value="${esc(b.f.min)}"><input id="f-max" class="short" type="number" placeholder="≤ MB" value="${esc(b.f.max)}">
        <button class="btn sm primary" id="f-apply">${icon('search')}${t('browse.filter')}</button></div>` : ''}
    </div>
    <div class="chat-body" id="b-body"></div>
    ${b.tab === 'files' ? `<div class="sel-bar"><span class="small" id="sel-info"></span><div class="btn-row"><button class="btn sm ghost" id="sel-all">${t('browse.selAll')}</button><button class="btn sm primary" id="sel-dl">${icon('download')}${t('browse.dlSel')}</button></div></div>` : ''}`;
  renderBody();
}
function fileTable(files, opts = {}) {
  return `<table class="file-table"><thead><tr>${opts.select ? '<th style="width:30px"></th>' : ''}<th>${t('col.name')}</th>${opts.chat ? `<th>${t('col.chat')}</th>` : ''}<th style="width:96px">${t('col.size')}</th><th style="width:136px">${t('col.date')}</th><th style="width:84px">${t('col.msg')}</th><th style="width:40px"></th></tr></thead><tbody>
    ${files.map(f => `<tr data-mid="${f.message_id}" data-link="${esc(f.link || '')}">${opts.select ? `<td><input type="checkbox" ${S.b.selected.has(f.message_id) ? 'checked' : ''}></td>` : ''}
      <td><div class="fname">${kindIco(f.kind)}<span class="n" title="${esc(f.name)}${f.caption ? '\n\n' + esc(f.caption) : ''}">${esc(f.name)}</span>${fileTags(f)}</div></td>
      ${opts.chat ? `<td class="muted small">${esc(f.chat || '')}</td>` : ''}
      <td class="num">${size(f.size)}</td><td class="num muted">${dateStr(f.date)}</td>
      <td>${f.link ? `<a href="${esc(f.link)}" target="_blank" class="mono">#${f.message_id}</a>` : '#' + f.message_id}</td>
      <td><button class="icon-btn" data-dl="${f.message_id}" title="Download">${icon('download')}</button></td></tr>`).join('')}</tbody></table>`;
}
function renderBody() {
  const b = S.b, body = $('#b-body');
  if (!body) return;
  if (b.tab === 'files') {
    const s = b.fileSummary, loaded = b.files.reduce((x, f) => x + f.size, 0);
    body.innerHTML = (s ? `<div class="summary-strip"><span>${t('browse.loaded', { n: `<b>${b.files.length}</b>` })}</span><span>${t('browse.total', { s: `<b>${size(loaded)}</b>` })}</span>
        <span>${t('browse.scanned', { n: `<b>${s.scanned}</b>` })}</span><span>${b.fileCursor ? t('browse.more') : t('browse.end')}</span></div>${archiveSets(s.sets)}` : '')
      + (b.files.length ? fileTable(b.files, { select: true }) : (b.loading ? '' : `<div class="empty">${t('browse.noFiles')}</div>`))
      + (b.loading ? `<div class="load-more">${icon('loader', 'spin')}</div>` : b.fileCursor ? `<div class="load-more"><button class="btn" id="more-files">${t('browse.loadMore')}</button></div>` : '');
    const si = $('#sel-info');
    if (si) { const sel = b.files.filter(f => b.selected.has(f.message_id)); si.textContent = sel.length ? t('browse.selected', { n: sel.length, s: size(sel.reduce((x, f) => x + f.size, 0)) }) : t('browse.selHint'); }
  } else {
    body.innerHTML = b.msgs.map(m => `<div class="msg"><div class="msg-head"><span>#${m.id}</span><span>${dateStr(m.date)}</span>
        ${m.sender ? `<span>${esc(m.sender.name || '')}</span>` : ''}${m.views != null ? `<span>${icon('eye')} ${m.views}</span>` : ''}${m.link ? `<a href="${esc(m.link)}" target="_blank">link</a>` : ''}</div>
      ${m.text ? `<div class="msg-text">${esc(m.text)}</div>` : ''}
      ${m.file ? `<div class="msg-file">${kindIco(m.file.kind)}<span>${esc(m.file.name)}</span><span class="muted">${size(m.file.size)}</span><button class="icon-btn" data-dl="${m.id}">${icon('download')}</button></div>` : ''}</div>`).join('')
      + (b.loading ? `<div class="load-more">${icon('loader', 'spin')}</div>` : b.msgCursor ? `<div class="load-more"><button class="btn" id="more-msgs">${t('browse.loadMore')}</button></div>` : (b.msgs.length ? '' : `<div class="empty">${t('browse.noMsgs')}</div>`));
  }
}
function fileArgs() {
  const f = S.b.f, a = { account: S.b.account, chat: String(S.b.chat) };
  if (f.types.length) a.types = f.types;
  if (f.name) a.name_contains = f.name;
  if (f.ext) a.extensions = f.ext.split(/[,\s]+/).filter(Boolean);
  if (f.min) a.min_size_mb = Number(f.min);
  if (f.max) a.max_size_mb = Number(f.max);
  return a;
}
async function loadFiles(more = false) {
  const b = S.b;
  b.loading = true; renderBody();
  try {
    const args = { ...fileArgs(), limit: 100, scan_limit: 2000 };
    if (more && b.fileCursor) args.offset_id = b.fileCursor;
    const r = await tool('tg_list_files', args);
    b.files = more ? b.files.concat(r.files) : r.files;
    b.fileCursor = r.next_offset_id;
    b.fileSummary = { scanned: (more && b.fileSummary ? b.fileSummary.scanned : 0) + r.scanned_messages, sets: r.archive_sets };
  } catch (e) { toast(e.message, false); }
  b.loading = false; renderBody();
}
async function loadMsgs(more = false) {
  const b = S.b;
  b.loading = true; renderBody();
  try {
    const args = { account: b.account, chat: String(b.chat), limit: 50, text_max: 2000 };
    if (more && b.msgCursor) args.offset_id = b.msgCursor;
    const r = await tool('tg_get_messages', args);
    b.msgs = more ? b.msgs.concat(r.messages) : r.messages;
    b.msgCursor = r.next_offset_id;
  } catch (e) { toast(e.message, false); }
  b.loading = false; renderBody();
}
async function downloadArgs(args) {
  try {
    const r = await tool('tg_download', args);
    toast(t('browse.queued', { n: r.queued, s: r.total_size_human }) + (r.added_archive_parts ? t('browse.addedParts', { n: r.added_archive_parts }) : '')
      + (r.skipped.length ? t('browse.skipped', { n: r.skipped.length }) : ''));
  } catch (e) { toast(e.message, false); }
}
const downloadIds = ids => ids.length ? downloadArgs({ account: S.b.account, chat: String(S.b.chat), message_ids: ids }) : toast(t('browse.pickFirst'), false);
function exportModal() {
  openModal(`<h3>${esc(t('exp.title', { t: S.b.info.title }))}</h3><p class="muted small">${t('exp.desc')}</p>
    <form><div class="row-2"><label>${t('exp.what')}<select name="what"><option value="files">${t('exp.files')}</option><option value="messages">${t('exp.msgs')}</option></select></label>
    <label>${t('exp.format')}<select name="format"><option value="csv">CSV</option><option value="json">JSON</option><option value="jsonl">JSONL</option><option value="md">Markdown</option></select></label></div>
    <label>${t('exp.limit')}<input name="limit" type="number"></label>
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('exp.start')}</button></div></form>`,
  async fd => {
    const args = { account: S.b.account, chat: String(S.b.chat), what: fd.get('what'), format: fd.get('format') };
    if (fd.get('limit')) args.limit = Number(fd.get('limit'));
    if (args.what === 'files') Object.assign(args, fileArgs());
    await tool('tg_export', args);
    toast(t('exp.started'));
  });
}
function indexModal(chat = '') {
  openModal(`<h3>${t('lib.idxTitle')}</h3><p class="muted small">${t('lib.idxDesc')}</p>
    <form><label>${t('watch.account')}<select name="account">${accountOptions(S.b.account || readyAccounts()[0]?.id)}</select></label>
    <label>${t('watch.chat')}<input name="chat" required value="${esc(chat)}" placeholder="@channel / t.me/…"></label>
    <label class="follow"><input type="checkbox" name="full">${t('lib.full2')}</label>
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('lib.idxStart')}</button></div></form>`,
  async fd => {
    await tool('tg_index_chat', { account: fd.get('account'), chat: fd.get('chat'), full: !!fd.get('full') });
    toast(t('lib.idxStarted'));
  });
}
function bindBrowse() {
  $('#b-account').onchange = e => { S.b.account = e.target.value; loadDialogs(); };
  let qt;
  $('#b-dialog-q').oninput = e => { clearTimeout(qt); qt = setTimeout(() => { S.b.q = e.target.value.trim(); loadDialogs(); }, 350); };
  $('#b-open').onkeydown = e => { if (e.key === 'Enter' && e.target.value.trim()) openChat(e.target.value.trim()); };
  $('#b-kind').onclick = e => { const k = e.target.dataset.k; if (!k) return; S.b.kind = k; $$('#b-kind button').forEach(b => b.classList.toggle('on', b === e.target)); loadDialogs(); };
  $('#b-dialogs').onclick = e => { const d = e.target.closest('.dialog'); if (d) openChat(d.dataset.id); };
  $('#b-chat').addEventListener('click', e => {
    const b = S.b, el = e.target;
    const tab = el.closest('#b-tab button');
    if (tab) { b.tab = tab.dataset.t; renderChat(); if (b.tab === 'files' && !b.files.length) loadFiles(); if (b.tab === 'msgs' && !b.msgs.length) loadMsgs(); return; }
    const chip = el.closest('.chip');
    if (chip) { const k = chip.dataset.type; b.f.types = b.f.types.includes(k) ? b.f.types.filter(x => x !== k) : [...b.f.types, k]; chip.classList.toggle('on'); return; }
    if (el.closest('#f-apply')) {
      Object.assign(b.f, { name: $('#f-name').value.trim(), ext: $('#f-ext').value.trim(), min: $('#f-min').value, max: $('#f-max').value });
      b.files = []; b.selected.clear(); b.fileSummary = null; loadFiles(); return;
    }
    if (el.closest('#more-files')) return loadFiles(true);
    if (el.closest('#more-msgs')) return loadMsgs(true);
    if (el.closest('#b-export')) return exportModal();
    if (el.closest('#b-index')) return indexModal(String(b.chat));
    const dl = el.closest('[data-dl]');
    if (dl) return downloadIds([Number(dl.dataset.dl)]);
    if (el.closest('#sel-all')) { const all = b.files.every(f => b.selected.has(f.message_id)); b.files.forEach(f => all ? b.selected.delete(f.message_id) : b.selected.add(f.message_id)); renderBody(); return; }
    if (el.closest('#sel-dl')) return downloadIds([...b.selected]);
    if (el.type === 'checkbox') { const mid = Number(el.closest('tr').dataset.mid); el.checked ? b.selected.add(mid) : b.selected.delete(mid); renderBody(); }
  });
  $('#b-chat').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.closest('.filters')) $('#f-apply').click(); });
}

/* ============================================================ library */
async function initLibrary() {
  renderLibFilters();
  try {
    const r = await tool('tg_index_status', {});
    S.lib.index = r.chats;
  } catch (e) { S.lib.index = []; }
  renderLibIndex();
  renderLibResults();
}
function renderLibFilters() {
  const L = S.lib;
  const chats = L.index.map(c => `<option value="${c.chat_id}" ${String(L.chat) === String(c.chat_id) ? 'selected' : ''}>${esc(c.title || c.chat_id)}</option>`).join('');
  $('#l-filters').innerHTML = ['document', 'video', 'audio', 'photo'].map(k => `<button class="chip ${L.types.includes(k) ? 'on' : ''}" data-type="${k}">${t('kind.' + k)}</button>`).join('')
    + `<input id="l-ext" class="short" placeholder="${t('browse.ext')}" value="${esc(L.ext)}"><input id="l-min" class="short" type="number" placeholder="≥ MB" value="${esc(L.min)}"><input id="l-max" class="short" type="number" placeholder="≤ MB" value="${esc(L.max)}">
      <select id="l-chat"><option value="">${t('lib.allChats')}</option>${chats}</select>
      <select id="l-sort"><option value="date">${t('lib.sortDate')}</option><option value="size" ${L.sort === 'size' ? 'selected' : ''}>${t('lib.sortSize')}</option><option value="name" ${L.sort === 'name' ? 'selected' : ''}>${t('lib.sortName')}</option></select>`;
  const opts = L.index.map(c => `<option value="${c.chat_id}">${esc(c.title || c.chat_id)} · ${c.files}</option>`).join('');
  $('#l-cmp-form').innerHTML = L.index.length < 2 ? `<div class="muted small">${t('lib.needTwo')}</div>` : `
    <label>${t('lib.cmpA')}<select id="cmp-a">${opts}</select></label>
    <label>${t('lib.cmpB')}<select id="cmp-b">${opts}</select></label>
    <label>${t('lib.cmpBy')}<select id="cmp-by"><option value="name_size">${t('lib.byNameSize')}</option><option value="name">${t('lib.byName')}</option><option value="stem">${t('lib.byStem')}</option><option value="file">${t('lib.byFile')}</option></select></label>
    <button class="btn primary sm" id="cmp-go" style="align-self:flex-start">${icon('scale')}${t('lib.run')}</button>`;
  if (L.index.length >= 2) $('#cmp-b').selectedIndex = 1;
}
function renderLibIndex() {
  const box = $('#l-index');
  if (!S.lib.index.length) { box.innerHTML = `<div class="muted small">${t('lib.noIndex')}</div>`; renderLibFilters(); return; }
  box.innerHTML = S.lib.index.map(c => `<div class="idx-item"><div class="idx-top"><span class="idx-title">${esc(c.title || c.chat_id)}</span>
      <span class="tag ${c.full_scan ? 'ok' : ''}">${c.full_scan ? t('lib.full') : t('lib.partial')}</span>
      <button class="icon-btn" data-reindex="${c.chat_id}" title="${t('lib.update')}">${icon('refresh')}</button></div>
    <div class="idx-meta">${t('lib.files', { n: c.files })} · ${size(c.total_size)} · ${ago(c.updated)}</div></div>`).join('');
  renderLibFilters();
}
function renderLibResults() {
  const r = S.lib.results, box = $('#l-results');
  if (!r) { box.innerHTML = `<div class="empty">${t(S.lib.index.length ? 'lib.empty' : 'lib.noIndex')}</div>`; return; }
  box.innerHTML = `<div class="summary-strip"><span>${t('lib.matched', { n: `<b>${r.matched}</b>`, s: `<b>${size(r.total_size)}</b>` })}</span></div>${archiveSets(r.archive_sets)}`
    + (r.files.length ? fileTable(r.files, { chat: true }) : `<div class="empty">${t('browse.noFiles')}</div>`);
}
async function runLibSearch() {
  const L = S.lib;
  L.q = $('#l-q').value.trim(); L.ext = $('#l-ext').value.trim(); L.min = $('#l-min').value; L.max = $('#l-max').value;
  L.chat = $('#l-chat').value; L.sort = $('#l-sort').value;
  const args = { query: L.q, sort: L.sort, limit: 200 };
  if (L.types.length) args.types = L.types;
  if (L.ext) args.extensions = L.ext.split(/[,\s]+/).filter(Boolean);
  if (L.min) args.min_size_mb = Number(L.min);
  if (L.max) args.max_size_mb = Number(L.max);
  if (L.chat) args.chats = [L.chat];
  try { L.results = await tool('tg_search_files', args); renderLibResults(); } catch (e) { toast(e.message, false); }
}
async function runCompare() {
  const a = $('#cmp-a').value, b = $('#cmp-b').value, by = $('#cmp-by').value;
  const box = $('#l-cmp-result');
  box.style.display = 'block';
  box.innerHTML = `<div class="empty">${icon('loader', 'spin')}</div>`;
  try {
    const r = await tool('tg_compare_chats', { chat_a: a, chat_b: b, by, sample: 40 });
    const col = (title, part) => `<div class="cmp-col"><h4>${title}</h4><div class="num-big">${part.count}</div><div class="muted small mono">${size(part.size)}</div>
      <ul>${part.sample.map(f => `<li title="${esc(f.name)}">${esc(f.name)} <span class="muted">${size(f.size)}</span></li>`).join('')}</ul></div>`;
    box.innerHTML = `<div class="card-head" style="margin:0"><h2>${esc(r.a.title)} ⇄ ${esc(r.b.title)}</h2><span class="label">${esc(by)}</span></div>
      <div class="cmp-grid">${col(t('lib.both'), r.in_both)}${col(t('lib.onlyA'), r.only_in_a)}${col(t('lib.onlyB'), r.only_in_b)}</div>`;
  } catch (e) { box.innerHTML = `<div class="empty" style="color:var(--err)">${esc(e.message)}</div>`; }
}
function bindLibrary() {
  $('#l-go').onclick = runLibSearch;
  $('#l-q').onkeydown = e => { if (e.key === 'Enter') runLibSearch(); };
  $('#l-filters').addEventListener('click', e => { const c = e.target.closest('.chip'); if (!c) return; const k = c.dataset.type; S.lib.types = S.lib.types.includes(k) ? S.lib.types.filter(x => x !== k) : [...S.lib.types, k]; c.classList.toggle('on'); });
  $('#l-filters').addEventListener('keydown', e => { if (e.key === 'Enter') runLibSearch(); });
  $('#l-add-index').onclick = () => indexModal();
  $('#l-index').onclick = async e => {
    const b = e.target.closest('[data-reindex]'); if (!b) return;
    try { await tool('tg_index_chat', { chat: b.dataset.reindex }); toast(t('lib.idxStarted')); } catch (err) { toast(err.message, false); }
  };
  $('#l-cmp-form').addEventListener('click', e => { if (e.target.closest('#cmp-go')) runCompare(); });
  $('#l-results').addEventListener('click', e => {
    const dl = e.target.closest('[data-dl]'); if (!dl) return;
    const link = dl.closest('tr').dataset.link;
    if (link) downloadArgs({ links: [link] });
  });
}

/* ============================================================ tasks */
function renderTasks() {
  const f = S.taskFilter;
  let list = [...S.tasks.values()].sort((a, b) => b.created - a.created);
  if (f === 'active') list = list.filter(tk => tk.kind === 'download' && ['approval', 'running', 'queued'].includes(tk.status));
  else if (f === 'jobs') list = list.filter(tk => tk.kind !== 'download');
  else if (f === 'done') list = list.filter(tk => tk.kind === 'download' && (tk.status === 'done' || tk.status === 'skipped'));
  else if (f === 'failed') list = list.filter(tk => tk.status === 'failed' || tk.status === 'canceled');
  else if (f !== 'all') list = list.filter(tk => tk.status === f);
  list = list.slice(0, 300);
  if (!list.length) { $('#task-list').innerHTML = `<div class="empty">${t('tasks.none')}</div>`; return; }
  $('#task-list').innerHTML = list.map(tk => {
    const p = pct(tk), dl = tk.kind === 'download';
    const acts = [];
    if (dl && (tk.status === 'running' || tk.status === 'queued')) acts.push(['pause', 'pause']);
    if (tk.status === 'paused') acts.push(['resume', 'play']);
    if (dl && (tk.status === 'failed' || tk.status === 'canceled')) acts.push(['retry', 'retry']);
    if ((tk.status === 'done' || tk.status === 'skipped') && tk.path) acts.push(['open', 'folder']);
    if (['approval', 'running', 'queued', 'paused'].includes(tk.status)) acts.push(['cancel', 'x', 'danger']);
    else acts.push(['remove', 'trash', 'danger']);
    return `<div class="task" data-id="${tk.id}">
      ${dl ? kindIco(tk.file_kind) : `<span class="kind-ico kind-document">${icon(tk.kind === 'index' ? 'database' : 'export')}</span>`}
      <div style="min-width:0"><div class="task-name" title="${esc(tk.path)}">${esc(tk.title)}</div>
        <div class="task-sub">${esc(tk.chat_title)} · ${who(tk.source)} · ${clock(tk.created)}${tk.error ? ` · <span class="err">${esc(tk.error)}</span>` : ''}${tk.note ? ` · ${esc(tk.note)}` : ''}</div></div>
      <div class="task-prog">${dl
        ? `<span class="num">${size(tk.done)} / ${size(tk.total)} · ${p.toFixed(1)}%</span><div class="bar ${tk.status}"><div style="width:${p}%"></div></div>`
        : `<span class="num">${t('tasks.scanned', { n: tk.done })}</span><div class="bar ${tk.status}"><div style="width:${tk.status === 'done' ? 100 : 50}%"></div></div>`}</div>
      <div class="task-speed">${waitText(tk) ? `<span class="tag warn">${esc(waitText(tk))}</span>`
        : tk.status === 'running' && dl ? `<div class="num">${size(tk.speed)}/s</div><div class="eta">${tk.eta != null ? dur(tk.eta) : ''}</div>` : taskTag(tk.status)}</div>
      <div class="task-actions">${acts.map(a => `<button class="icon-btn ${a[2] || ''}" title="${t('act.' + a[0])}" data-act="${a[0]}">${icon(a[1])}</button>`).join('')}</div>
    </div>`;
  }).join('');
}
function bindTasks() {
  $('#t-filter').onclick = e => { const s = e.target.dataset.s; if (!s) return; S.taskFilter = s; $$('#t-filter button').forEach(b => b.classList.toggle('on', b === e.target)); render(); };
  $$('[data-bulk]').forEach(b => b.onclick = async () => {
    try { const r = await post('/api/tasks/control', { action: b.dataset.bulk, all: true }); toast(t('tasks.handled', { n: r.affected })); } catch (e) { toast(e.message, false); }
  });
  $('#open-dl-dir').onclick = () => post('/api/open', {}).catch(e => toast(e.message, false));
  $('#task-list').onclick = async e => {
    const btn = e.target.closest('[data-act]'); if (!btn) return;
    const id = btn.closest('.task').dataset.id, act = btn.dataset.act;
    try {
      if (act === 'open') await post('/api/open', { path: S.tasks.get(id).path });
      else { await post('/api/tasks/control', { action: act, task_ids: [id] }); if (act === 'remove') { S.tasks.delete(id); render(); } }
    } catch (err) { toast(err.message, false); }
  };
}

/* ============================================================ watches */
function watchFilterText(w) {
  const f = w.filters || {}, parts = [];
  if (f.types?.length) parts.push(f.types.map(k => t('kind.' + k)).join('/'));
  if (f.name_contains) parts.push(`"${f.name_contains}"`);
  if (f.extensions?.length) parts.push(f.extensions.map(x => '.' + x).join(' '));
  if (f.min_size_mb) parts.push(`≥${f.min_size_mb}MB`);
  if (f.max_size_mb) parts.push(`≤${f.max_size_mb}MB`);
  return parts.join(' · ') || t('watch.any');
}
function renderWatches() {
  const grid = $('#w-grid');
  if (!S.watches.length) { grid.innerHTML = `<div class="empty">${t('watch.none')}</div>`; return; }
  grid.innerHTML = S.watches.map(w => `<div class="card watch ${w.pending_approval ? 'pending' : ''}" data-id="${w.id}">
    <div class="acc-top">${avatar(w.chat_title)}<div style="flex:1;min-width:0"><div class="acc-name">${esc(w.chat_title)}</div>
      <div class="small muted mono">${esc(w.account)} · ${t('watch.every', { n: w.interval_min })}</div></div>
      ${w.pending_approval ? `<span class="tag info">${t('watch.pending')}</span>` : `<button class="switch ${w.enabled ? 'on' : ''}" data-toggle></button>`}</div>
    <dl class="acc-kv"><dt>${t('watch.filter')}</dt><dd>${esc(watchFilterText(w))}</dd>
      <dt>${t('watch.last')}</dt><dd>${w.last_check ? ago(w.last_check) : t('watch.never')}${w.last_error ? ` · <span style="color:var(--err)">${esc(w.last_error)}</span>` : ''}</dd>
      <dt>${t('watch.got')}</dt><dd class="mono">${w.downloaded}</dd><dt>${t('watch.from')}</dt><dd>${who(w.source)}</dd>
      ${w.subdir ? `<dt>${t('watch.subdir')}</dt><dd class="mono">${esc(w.subdir)}</dd>` : ''}</dl>
    <div class="btn-row">${w.pending_approval ? `<button class="btn sm primary" data-wact="approve">${icon('check')}${t('watch.approve')}</button>` : `<button class="btn sm" data-wact="check">${icon('refresh')}${t('watch.check')}</button>`}
      <button class="btn ghost sm danger" data-wact="remove">${icon('trash')}${t('acc.remove')}</button></div></div>`).join('');
}
function watchModal() {
  const ready = readyAccounts();
  openModal(`<h3>${t('watch.add')}</h3><p class="muted small">${t('watch.intro')}</p><form>
    <div class="row-2"><label>${t('watch.account')}<select name="account">${accountOptions((ready.find(a => a.is_default) || ready[0])?.id)}</select></label>
      <label>${t('watch.chat')}<input name="chat" required placeholder="@channel / t.me/…"></label></div>
    <div class="filters" style="padding:0">${['document', 'video', 'audio', 'photo'].map(k => `<label class="follow" style="padding:0"><input type="checkbox" name="type" value="${k}">${t('kind.' + k)}</label>`).join('')}</div>
    <div class="row-2"><label>${t('browse.nameHas')}<input name="name_contains"></label><label>${t('browse.ext')}<input name="extensions" placeholder="zip, mp4"></label></div>
    <div class="row-2"><label>≥ MB<input name="min" type="number"></label><label>≤ MB<input name="max" type="number"></label></div>
    <div class="row-2"><label>${t('watch.interval')}<input name="interval" type="number" min="5" value="30"></label><label>${t('watch.recent')}<input name="recent" type="number" min="0" value="0"></label></div>
    <label>${t('watch.subdir')}<input name="subdir"></label>
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('watch.create')}</button></div></form>`,
  async fd => {
    const filters = {};
    const types = fd.getAll('type'); if (types.length) filters.types = types;
    if (fd.get('name_contains')) filters.name_contains = fd.get('name_contains');
    if (fd.get('extensions')) filters.extensions = fd.get('extensions').split(/[,\s]+/).filter(Boolean);
    if (fd.get('min')) filters.min_size_mb = Number(fd.get('min'));
    if (fd.get('max')) filters.max_size_mb = Number(fd.get('max'));
    await post('/api/watches', { account: fd.get('account'), chat: fd.get('chat'), filters, interval_min: Number(fd.get('interval') || 30),
                                 include_recent: Number(fd.get('recent') || 0), subdir: fd.get('subdir') || '' });
    await refreshApprovals();
  });
}
function bindWatches() {
  $('#w-add').onclick = watchModal;
  $('#w-grid').onclick = async e => {
    const card = e.target.closest('.watch'); if (!card) return;
    const id = card.dataset.id, w = S.watches.find(x => x.id === id);
    try {
      if (e.target.closest('[data-toggle]')) await api(`/api/watches/${id}`, { method: 'PATCH', body: { enabled: !w.enabled } });
      const a = e.target.closest('[data-wact]')?.dataset.wact;
      if (a === 'approve') await api(`/api/watches/${id}`, { method: 'PATCH', body: { approve: true } });
      if (a === 'remove') { if (!confirmBox(t('watch.removeConfirm'))) return; await api(`/api/watches/${id}`, { method: 'DELETE' }); }
      if (a === 'check') { const r = await post(`/api/watches/${id}/check`); toast(t('watch.found', { n: r.queued })); }
      await refreshApprovals();
    } catch (err) { toast(err.message, false); }
  };
}

/* ============================================================ accounts */
function renderAccounts() {
  const grid = $('#acc-grid');
  if (grid.contains(document.activeElement) && document.activeElement.tagName === 'INPUT') return;
  grid.innerHTML = S.accounts.map(a => {
    const px = a.effective_proxy;
    const pxs = px && px.type ? `${px.type}://${px.host}:${px.port}` : t('acc.direct');
    let login = '';
    const qr = S.qr[a.id];
    if (a.status === 'qr_waiting' && qr) {
      const left = Math.max(0, Math.round(qr.expires - Date.now() / 1000));
      login = `<div class="login-box"><div class="qr-box"><div class="qr">${qr.svg}</div><div class="small">${t('acc.qrScan')}<div class="muted mono" style="margin-top:6px">${t('acc.qrExpire', { n: left })}</div>
        <button class="btn ghost sm" data-acc="qr_cancel" style="margin-top:10px">${t('acc.cancel')}</button></div></div></div>`;
    } else if (['need_login', 'qr_waiting'].includes(a.status)) {
      login = `<div class="login-box"><div class="small muted">${t('acc.needLogin')}</div>
        <div class="btn-row"><button class="btn primary" data-acc="qr">${icon('qr')}${t('acc.qrLogin')}</button>
        <button class="btn" data-acc="send_code" ${a.has_phone ? '' : `disabled title="${esc(t('acc.noPhone'))}"`}>${icon('bolt')}${t('acc.codeLogin')}</button></div></div>`;
    } else if (a.status === 'code_sent') {
      login = `<div class="login-box"><div class="small">${t('acc.enterCode')}</div>
        <div class="row"><input data-in="code" placeholder="${t('acc.code')}" autocomplete="one-time-code"><button class="btn primary" data-acc="code">${t('acc.login')}</button></div>
        <button class="btn ghost sm" data-acc="send_code" style="align-self:flex-start">${t('acc.resend')}</button></div>`;
    } else if (a.status === 'password_needed') {
      login = `<div class="login-box"><div class="small">${t('acc.need2fa')}</div>
        <div class="row"><input data-in="password" type="password" placeholder="${t('acc.password')}" autocomplete="current-password"><button class="btn primary" data-acc="password">${t('acc.confirm')}</button></div></div>`;
    } else if (a.status === 'error' || a.status === 'disconnected') {
      login = `<div class="login-box"><div class="small" style="color:var(--err)">${esc(a.error || t('st.disconnected'))}</div>
        <div><button class="btn" data-acc="connect">${icon('refresh')}${t('acc.reconnect')}</button></div></div>`;
    }
    return `<div class="card acc-card" data-id="${esc(a.id)}">
      <div class="acc-top">${avatar(a.name)}<div style="flex:1;min-width:0"><div class="acc-name">${esc(a.name)} ${a.is_default ? `<span class="tag info">${t('acc.default')}</span>` : ''}</div>
        <div class="small muted">${a.me ? esc((a.me.name || '') + (a.me.username ? ' · @' + a.me.username : '')) : esc(a.phone)}</div></div>${statusTag(a.status)}</div>
      <dl class="acc-kv"><dt>${t('acc.id')}</dt><dd class="mono">${esc(a.id)}</dd><dt>${t('acc.phoneL')}</dt><dd>${esc(a.phone || '—')}</dd>
        <dt>api_id</dt><dd class="mono">${esc(a.api_id)}</dd><dt>${t('acc.proxy')}</dt><dd class="mono">${esc(pxs)}${a.proxy == null ? ` <span class="muted">${t('acc.follow')}</span>` : ''}</dd>
        ${a.me ? `<dt>${t('acc.uid')}</dt><dd class="mono">${a.me.id}${a.me.premium ? ' <span class="tag warn">Premium</span>' : ''}</dd>` : ''}</dl>
      ${login}
      <div class="btn-row">${a.is_default ? '' : `<button class="btn ghost sm" data-acc="default">${icon('star')}${t('acc.setDefault')}</button>`}
        <button class="btn ghost sm" data-acc="edit">${icon('edit')}${t('acc.edit')}</button>
        <button class="btn ghost sm danger" data-acc="remove">${icon('trash')}${t('acc.remove')}</button></div></div>`;
  }).join('') + `<div class="card add-card" id="add-acc"><div>${icon('plus')}${t('acc.add')}</div></div>`;
}
function proxyFields(p) {
  p = p || {};
  return `<div class="row-3" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">
    <label>${t('acc.ptype')}<select name="ptype"><option value="__default" ${p.__default ? 'selected' : ''}>${t('acc.pfollow')}</option><option value="" ${!p.__default && !p.type ? 'selected' : ''}>${t('set.direct')}</option>
      <option value="socks5" ${p.type === 'socks5' ? 'selected' : ''}>SOCKS5</option><option value="http" ${p.type === 'http' ? 'selected' : ''}>HTTP</option></select></label>
    <label>${t('set.host')}<input name="phost" value="${esc(p.host || '')}" placeholder="127.0.0.1"></label>
    <label>${t('set.port')}<input name="pport" type="number" value="${esc(p.port || '')}" placeholder="7890"></label></div>`;
}
function readProxy(fd) {
  const ty = fd.get('ptype');
  if (ty === '__default') return null;
  if (!ty) return { type: '' };
  return { type: ty, host: fd.get('phost') || '127.0.0.1', port: Number(fd.get('pport') || 7890) };
}
function addAccountModal() {
  openModal(`<h3>${t('acc.add')}</h3><p class="muted small">${t('acc.addDesc')}</p>
    <form><label>${t('acc.name')}<input name="name"></label>
    <div class="row-2"><label>api_id<input name="api_id" required inputmode="numeric"></label><label>api_hash<input name="api_hash" required></label></div>
    <label>${t('acc.phone')}<input name="phone" placeholder="+8613800000000"></label>
    ${proxyFields({ __default: true })}
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('acc.addGo')}</button></div></form>`,
  async fd => {
    await post('/api/accounts', { name: fd.get('name'), api_id: fd.get('api_id'), api_hash: fd.get('api_hash'), phone: fd.get('phone'), proxy: readProxy(fd) });
    toast(t('acc.added'));
    setTimeout(loadAccounts, 1500);
  });
}
function editAccountModal(a) {
  openModal(`<h3>${t('acc.edit')} · ${esc(a.name)}</h3><form>
    <label>${t('acc.name')}<input name="name" value="${esc(a.name)}"></label>
    <div class="row-2"><label>api_id<input name="api_id" value="${esc(a.api_id)}"></label><label>api_hash<input name="api_hash" placeholder="${t('acc.hashKeep')}"></label></div>
    <label>${t('acc.phone')}<input name="phone" placeholder="${esc(a.phone || '+8613800000000')}"></label>
    ${proxyFields(a.proxy == null ? { __default: true } : a.proxy)}
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary">${t('set.save')}</button></div></form>`,
  async fd => {
    const body = { name: fd.get('name'), api_id: fd.get('api_id'), proxy: readProxy(fd) };
    if (fd.get('api_hash')) body.api_hash = fd.get('api_hash');
    if (fd.get('phone')) body.phone = fd.get('phone');
    await api(`/api/accounts/${a.id}`, { method: 'PATCH', body });
    toast(t('acc.saved'));
    setTimeout(loadAccounts, 1200);
  });
}
function removeAccountModal(a) {
  openModal(`<h3>${esc(t('acc.removeT', { n: a.name }))}</h3><p class="muted small">${t('acc.removeD')}</p>
    <form><label class="follow"><input type="checkbox" name="logout">${t('acc.logout')}</label>
    <div class="modal-foot"><button type="button" class="btn ghost" data-close>${t('common.cancel')}</button><button type="submit" class="btn primary" style="background:var(--err);border-color:var(--err)">${t('acc.remove')}</button></div></form>`,
  async fd => { await api(`/api/accounts/${a.id}?logout=${fd.get('logout') ? 'true' : 'false'}`, { method: 'DELETE' }); loadAccounts(); });
}
let qrTimer = null;
function pollQr() {
  clearInterval(qrTimer);
  qrTimer = setInterval(async () => {
    const ids = Object.keys(S.qr);
    if (!ids.length) { clearInterval(qrTimer); return; }
    for (const id of ids) {
      try {
        const r = await api(`/api/accounts/${id}/qr`);
        if (r.status === 'qr_waiting' && r.svg) S.qr[id] = r;
        else { delete S.qr[id]; if (r.status === 'ready') toast(t('acc.loggedIn')); await loadAccounts(); }
      } catch (e) { delete S.qr[id]; }
    }
    if (S.page === 'accounts') renderAccounts();
  }, 2500);
}
async function accountAction(id, act, card) {
  const a = S.accounts.find(x => x.id === id);
  try {
    if (act === 'edit') return editAccountModal(a);
    if (act === 'remove') return removeAccountModal(a);
    if (act === 'default') await post(`/api/accounts/${id}/default`);
    if (act === 'connect') { toast(t('acc.connecting')); await post(`/api/accounts/${id}/connect`); }
    if (act === 'send_code') { await post(`/api/accounts/${id}/send_code`); toast(t('acc.codeSent')); }
    if (act === 'code') await post(`/api/accounts/${id}/code`, { code: $('[data-in=code]', card).value });
    if (act === 'password') await post(`/api/accounts/${id}/password`, { password: $('[data-in=password]', card).value });
    if (act === 'qr') { const r = await post(`/api/accounts/${id}/qr`); if (r.svg) { S.qr[id] = r; pollQr(); } }
    if (act === 'qr_cancel') { delete S.qr[id]; await post(`/api/accounts/${id}/connect`); }
  } catch (e) { toast(e.message, false); }
  document.activeElement?.blur();
  await loadAccounts();
}
function bindAccounts() {
  $('#acc-grid').onclick = e => {
    if (e.target.closest('#add-acc')) return addAccountModal();
    const btn = e.target.closest('[data-acc]'); if (!btn) return;
    const card = btn.closest('.acc-card');
    accountAction(card.dataset.id, btn.dataset.acc, card);
  };
  $('#acc-grid').addEventListener('keydown', e => {
    if (e.key !== 'Enter' || !e.target.dataset.in) return;
    const card = e.target.closest('.acc-card');
    accountAction(card.dataset.id, e.target.dataset.in, card);
  });
}

/* ============================================================ connect */
async function renderConnect() {
  if (!S.token) { try { S.token = (await api('/api/token')).token; } catch (e) { /* login screen */ } }
  const tok = S.token;
  $('#c-token').textContent = S.tokenShown ? tok : '•'.repeat(24);
  $('#c-reveal').textContent = S.tokenShown ? t('connect.hide') : t('connect.reveal');
  const p = S.paths, win = (p.platform || '').startsWith('win');
  const url = `http://127.0.0.1:${S.port}/mcp`;
  const cmd = p.frozen ? [p.python, 'mcp'] : p.checkout ? [p.python, `${p.root}${win ? '\\' : '/'}mcp_stdio.py`] : ['tg-agent-mcp'];
  const j = s => JSON.stringify(s);
  const mask = s => S.tokenShown ? s : s.replaceAll(tok, '<TOKEN>');
  const blocks = [
    ['Claude Code', [[t('connect.ccHttp'), `claude mcp add --transport http --scope user tg-agent ${url} --header "Authorization: Bearer ${tok}"`],
                     [t('connect.ccStdio'), `claude mcp add --scope user tg-agent -- ${cmd.map(c => `"${c}"`).join(' ')}`]]],
    ['Codex', [[t('connect.codex'), `[mcp_servers.tg-agent]\ncommand = ${j(cmd[0])}\nargs = [${cmd.slice(1).map(j).join(', ')}]\nstartup_timeout_sec = 20\ntool_timeout_sec = 600`]]],
    [t('connect.other'), [[t('connect.json'), `{\n  "mcpServers": {\n    "tg-agent": {\n      "command": ${j(cmd[0])},\n      "args": [${cmd.slice(1).map(j).join(', ')}]\n    }\n  }\n}`],
                          [t('connect.http'), `{\n  "url": "${url}",\n  "headers": { "Authorization": "Bearer ${tok}" }\n}`]]],
    [t('connect.try'), [[t('connect.tryDesc'), t('connect.tryText')]]],
  ];
  $('#connect-grid').innerHTML = blocks.map(([title, rows]) => `<div class="card"><h2>${esc(title)}</h2>${rows.map(([d, code]) =>
    `<div class="step">${esc(d)}</div><div class="code" data-copy="${esc(code)}"><button class="icon-btn copy" title="Copy">${icon('copy')}</button><span>${esc(mask(code))}</span></div>`).join('')}</div>`).join('');
  const tools = Object.values(S.toolsMeta);
  $('#tool-count').textContent = t('connect.nTools', { n: tools.length });
  $('#tool-list').innerHTML = tools.map(x => `<div class="tool"><div class="tool-name">${esc(x.name)}<span class="tag ${x.read_only ? 'ok' : 'info'}">${x.read_only ? t('connect.ro') : t('connect.task')}</span></div><div class="tool-desc">${esc(LANG === 'zh' ? x.title_zh : x.title_en)} — ${esc(x.description)}</div></div>`).join('');
}
function bindConnect() {
  $('#c-reveal').onclick = () => { S.tokenShown = !S.tokenShown; renderConnect(); };
  $('#c-regen').onclick = async () => {
    if (!confirmBox(t('connect.regenConfirm'))) return;
    S.token = (await post('/api/token/regenerate')).token;
    toast(t('connect.regened'));
    renderConnect();
  };
  document.addEventListener('click', e => {
    const c = e.target.closest('.copy'); if (!c) return;
    const box = c.closest('[data-copy]');
    navigator.clipboard.writeText(box ? box.dataset.copy : c.nextElementSibling.textContent).then(() => toast(t('connect.copied')));
  });
}

/* ============================================================ settings */
function fillSettings() {
  const f = $('#settings-form'), s = S.settings;
  for (const k of ['language', 'download_dir', 'name_template', 'max_concurrent_files', 'connections_per_file', 'read_wait_time', 'approval_size_gb', 'approval_files',
                   'speed_limit_kbps', 'download_window_start', 'download_window_end']) f.elements[k].value = s[k] ?? '';
  f.elements.dedupe_downloads.checked = s.dedupe_downloads !== false;
  f.elements.check_updates.checked = s.check_updates !== false;
  $('#notify-toggle').checked = notifyEnabled();
  f.elements.part_size_kb.value = String(s.part_size_kb || 512);
  f.elements.workflow_idle_min.value = Math.round((s.workflow_idle_seconds || 1800) / 60);
  const p = s.default_proxy || {};
  f.elements.proxy_type.value = p.type || '';
  f.elements.proxy_host.value = p.host || '';
  f.elements.proxy_port.value = p.port || '';
}
function bindSettings() {
  $('#notify-toggle').onchange = async e => {
    if (!e.target.checked) { setNotify(false); return; }
    const p = 'Notification' in window ? await Notification.requestPermission() : 'denied';
    if (p !== 'granted') { e.target.checked = false; toast(t('n.denied'), false); return; }
    setNotify(true);
  };
  $('#settings-form').onsubmit = async e => {
    e.preventDefault();
    const f = e.target.elements;
    const body = {
      language: f.language.value, download_dir: f.download_dir.value.trim(), name_template: f.name_template.value.trim(),
      max_concurrent_files: Number(f.max_concurrent_files.value), connections_per_file: Number(f.connections_per_file.value),
      part_size_kb: Number(f.part_size_kb.value), read_wait_time: Number(f.read_wait_time.value),
      approval_size_gb: Number(f.approval_size_gb.value), approval_files: Number(f.approval_files.value),
      workflow_idle_seconds: Number(f.workflow_idle_min.value || 30) * 60,
      speed_limit_kbps: Number(f.speed_limit_kbps.value || 0),
      download_window_start: f.download_window_start.value || '', download_window_end: f.download_window_end.value || '',
      dedupe_downloads: f.dedupe_downloads.checked, check_updates: f.check_updates.checked,
      default_proxy: f.proxy_type.value ? { type: f.proxy_type.value, host: f.proxy_host.value || '127.0.0.1', port: Number(f.proxy_port.value || 7890) } : { type: '' },
    };
    try { S.settings = await post('/api/settings', body); setLang(S.settings.language); toast(t('set.saved')); fillSettings(); } catch (err) { toast(err.message, false); }
  };
}
