'use strict';
/* TG Agent console — core: icons, i18n, helpers, API, shared state. */

const ICONS = {
  flow: '<rect x="3" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="16" width="7" height="5" rx="1.5"/><path d="M6.5 8v4a3 3 0 0 0 3 3h8V16"/>',
  pulse: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
  database: '<ellipse cx="12" cy="5.5" rx="8" ry="2.5"/><path d="M4 5.5v13c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5v-13M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  plug: '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  link: '<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  play: '<path d="M7 4l13 8-13 8z"/>',
  retry: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  alert: '<path d="M12 3l10 18H2zM12 10v5M12 18v.5"/>',
  loader: '<path d="M12 3a9 9 0 1 0 9 9"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>',
  audio: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  photo: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  star: '<path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  export: '<path d="M12 15V3M7 8l5-5 5 5M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4"/>',
  shield: '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 17h4v4h-4"/>',
  scale: '<path d="M12 3v18M5 7h14M7 7l-3 7a3 3 0 0 0 6 0zM17 7l-3 7a3 3 0 0 0 6 0z"/>',
};
const icon = (n, cls = '') => `<i data-icon="${n}" class="${cls}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ICONS[n] || ''}</svg></i>`;
function hydrateIcons(root = document) {
  root.querySelectorAll('i[data-icon]:empty').forEach(el => { el.outerHTML = icon(el.dataset.icon, el.className); });
}

/* ------------------------------------------------------------ i18n */
const I18N = {
  zh: {
    'nav.section': '工作区', 'page.workflow': '工作流', 'page.browse': '浏览频道', 'page.library': '文件库', 'page.tasks': '任务',
    'page.watches': '订阅', 'page.accounts': '账号', 'page.connect': '接入 AI', 'page.settings': '设置',
    'conn.ok': '服务运行中', 'conn.bad': '服务未连接',
    'wf.flows': '工作流', 'wf.log': '日志', 'wf.search': '搜索工作流', 'wf.follow': '自动跟随最新活动',
    'wf.active': '进行中', 'wf.today': '今天', 'wf.earlier': '更早', 'wf.untitled': '未命名工作流', 'wf.none': '还没有工作流。接入 AI 后，它的每次请求都会在这里显示为一条工作流。',
    'wf.pick': '从左侧选择一个工作流', 'wf.steps': '{n} 步', 'wf.polls': '已查询进度 ×{n}', 'wf.waiting': '等待 AI 的下一步…',
    'wf.finished': '已完成', 'wf.failedEnd': '已结束（失败）', 'wf.idleEnd': '已结束', 'wf.implicitTip': 'AI 没有调用 tg_start_workflow，这些调用被归入未命名工作流',
    'wf.delete': '删除', 'wf.deleteConfirm': '删除这条工作流记录？', 'wf.started': '开始于', 'wf.duration': '用时', 'wf.noSteps': '还没有步骤',
    'wf.args': '参数', 'wf.result': '结果', 'wf.error': '错误', 'wf.tasks': '关联任务', 'wf.step': '步骤详情', 'wf.more': '还有 {n} 个',
    'wf.renameHint': '点击标题可重命名', 'log.empty': '还没有日志',
    'status.active': '进行中', 'status.done': '完成', 'status.failed': '失败', 'status.idle': '已结束', 'status.canceled': '已取消', 'status.running': '运行中', 'status.error': '出错',
    'ap.title': '{agent} 想下载 {n} 个文件（{size}）', 'ap.approve': '批准', 'ap.reject': '拒绝', 'ap.node': '等待你批准：{n} 个文件 · {size}',
    'ap.watch': '{agent} 创建了订阅：{chat}', 'ap.done': '已批准', 'ap.rejected': '已拒绝',
    'task.approval': '待批准', 'task.queued': '排队中', 'task.running': '下载中', 'task.paused': '已暂停', 'task.done': '完成', 'task.failed': '失败', 'task.canceled': '已取消', 'task.skipped': '已存在',
    'tasks.active': '进行中', 'tasks.paused': '已暂停', 'tasks.done': '已完成', 'tasks.failed': '失败', 'tasks.jobs': '导出与索引', 'tasks.all': '全部',
    'tasks.pauseAll': '全部暂停', 'tasks.resumeAll': '全部继续', 'tasks.retryFailed': '重试失败', 'tasks.openDir': '下载目录', 'tasks.none': '没有符合条件的任务',
    'tasks.scanned': '已扫描 {n} 条', 'tasks.handled': '已处理 {n} 个任务',
    'act.pause': '暂停', 'act.resume': '继续', 'act.retry': '重试', 'act.open': '打开所在位置', 'act.cancel': '取消', 'act.remove': '从列表移除',
    'browse.searchDialogs': '搜索已加入的对话', 'browse.open': '@用户名 或 t.me 链接，回车打开', 'browse.all': '全部', 'browse.channels': '频道', 'browse.groups': '群组', 'browse.users': '私聊',
    'browse.pick': '从左侧选择一个对话，或输入公开频道的用户名 / 链接', 'browse.noAccount': '没有可用账号，请先到「账号」页登录', 'browse.loading': '加载中…', 'browse.none': '没有结果',
    'browse.files': '文件', 'browse.msgs': '消息', 'browse.export': '导出清单', 'browse.index': '建立索引', 'browse.openTg': '打开', 'browse.nameHas': '文件名包含', 'browse.ext': '扩展名',
    'browse.filter': '筛选', 'browse.loaded': '已加载 {n} 个文件', 'browse.total': '共 {s}', 'browse.scanned': '已扫描 {n} 条消息', 'browse.more': '还有更多', 'browse.end': '已到末尾',
    'browse.loadMore': '加载更多', 'browse.noFiles': '没有符合条件的文件', 'browse.noMsgs': '没有消息', 'browse.selAll': '全选已加载', 'browse.dlSel': '下载所选', 'browse.selHint': '勾选文件后批量下载',
    'browse.selected': '已选 {n} 个 · {s}', 'browse.private': '私有', 'browse.members': '{n} 名成员', 'browse.latest': '最新 #{n}', 'browse.notJoined': '尚未加入',
    'browse.queued': '已加入下载队列：{n} 个文件，{s}', 'browse.skipped': '（跳过 {n}）', 'browse.pickFirst': '请先选择文件',
    'col.name': '文件名', 'col.size': '大小', 'col.date': '日期', 'col.msg': '消息', 'col.chat': '对话',
    'type.channel': '频道', 'type.supergroup': '超级群', 'type.group': '群组', 'type.user': '用户', 'type.bot': '机器人',
    'kind.document': '文档', 'kind.video': '视频', 'kind.audio': '音频', 'kind.photo': '图片', 'kind.voice': '语音',
    'exp.title': '导出 {t}', 'exp.desc': '在后台扫描整个对话并生成文件，适合大频道。', 'exp.what': '内容', 'exp.files': '文件清单', 'exp.msgs': '消息记录',
    'exp.format': '格式', 'exp.limit': '最多条数（留空为全部）', 'exp.start': '开始导出', 'exp.started': '导出已开始',
    'lib.searchPh': '在本地索引中搜索文件名或说明（不请求 Telegram）', 'lib.search': '搜索', 'lib.indexed': '已索引的对话', 'lib.indexChat': '索引对话',
    'lib.compare': '对比两个对话', 'lib.allChats': '全部对话', 'lib.sortDate': '按日期', 'lib.sortSize': '按大小', 'lib.sortName': '按名称', 'lib.matched': '匹配 {n} 个 · {s}',
    'lib.noIndex': '还没有索引。浏览频道、列出文件或点「索引对话」都会把文件写入本地索引。', 'lib.full': '完整', 'lib.partial': '部分', 'lib.update': '更新',
    'lib.files': '{n} 个文件', 'lib.cmpA': '对话 A', 'lib.cmpB': '对话 B', 'lib.cmpBy': '比较方式', 'lib.byName': '文件名', 'lib.byNameSize': '文件名 + 大小', 'lib.byStem': '去掉扩展名与符号', 'lib.byFile': '同一个 Telegram 文件',
    'lib.run': '对比', 'lib.both': '两边都有', 'lib.onlyA': '仅在 A', 'lib.onlyB': '仅在 B', 'lib.idxTitle': '索引一个对话', 'lib.idxDesc': '在后台扫描对话的全部文件写入本地索引；之后搜索和对比都不再请求 Telegram。再次索引只扫描新消息。',
    'lib.full2': '从头重新扫描', 'lib.idxStart': '开始索引', 'lib.idxStarted': '索引已开始', 'lib.needTwo': '至少需要两个已索引的对话', 'lib.empty': '输入关键词或设置筛选条件后搜索',
    'watch.title': '订阅频道', 'watch.intro': '定时检查对话，把符合条件的新文件自动加入下载。AI 创建的订阅需要你批准后才会启用。', 'watch.add': '新建订阅',
    'watch.none': '还没有订阅', 'watch.pending': '待批准', 'watch.every': '每 {n} 分钟', 'watch.last': '上次检查', 'watch.never': '从未', 'watch.got': '已下载', 'watch.from': '来源',
    'watch.check': '立即检查', 'watch.approve': '批准并启用', 'watch.filter': '筛选', 'watch.any': '所有文件', 'watch.interval': '检查间隔（分钟）', 'watch.recent': '同时检查最近 N 条消息',
    'watch.subdir': '保存到子文件夹', 'watch.chat': '对话', 'watch.account': '账号', 'watch.create': '创建', 'watch.removeConfirm': '删除这个订阅？', 'watch.found': '找到 {n} 个新文件',
    'acc.add': '添加账号', 'acc.addDesc': '在 my.telegram.org → API development tools 获取 api_id 与 api_hash。api_hash 会加密保存。',
    'acc.name': '显示名称', 'acc.phone': '手机号（国际格式，扫码登录可留空）', 'acc.addGo': '添加并连接', 'acc.edit': '编辑', 'acc.remove': '移除', 'acc.default': '默认', 'acc.setDefault': '设为默认',
    'acc.id': '账号 ID', 'acc.phoneL': '手机号', 'acc.proxy': '代理', 'acc.follow': '(跟随默认)', 'acc.uid': '用户 ID', 'acc.direct': '直连',
    'acc.needLogin': '此账号尚未登录，选择登录方式：', 'acc.qrLogin': '扫码登录', 'acc.codeLogin': '验证码登录', 'acc.enterCode': '请输入收到的验证码', 'acc.code': '验证码', 'acc.login': '登录', 'acc.resend': '重新发送',
    'acc.need2fa': '此账号开启了两步验证，请输入密码（不会保存）', 'acc.password': '两步验证密码', 'acc.confirm': '确认', 'acc.reconnect': '重新连接', 'acc.connecting': '正在连接…',
    'acc.qrScan': '用手机 Telegram 扫描：设置 → 设备 → 连接桌面设备', 'acc.qrExpire': '{n} 秒后刷新', 'acc.cancel': '取消',
    'acc.removeT': '移除账号 {n}？', 'acc.removeD': '会删除本地保存的登录会话。勾选下方选项会同时在 Telegram 服务器上注销该会话。', 'acc.logout': '同时在 Telegram 上注销此会话',
    'acc.saved': '已保存', 'acc.added': '账号已添加，正在连接…', 'acc.codeSent': '验证码已发送', 'acc.loggedIn': '登录成功', 'acc.noPhone': '没有手机号，请用扫码登录或编辑账号添加手机号',
    'acc.hashKeep': '留空则不修改', 'acc.ptype': '代理类型', 'acc.pfollow': '跟随默认', 'acc.none': '未添加账号',
    'st.ready': '已就绪', 'st.connecting': '连接中', 'st.need_login': '需要登录', 'st.code_sent': '等待验证码', 'st.password_needed': '需要两步验证', 'st.qr_waiting': '等待扫码', 'st.error': '连接失败', 'st.disconnected': '未连接',
    'connect.title': '把 TG Agent 接入你的 AI 工具', 'connect.intro': 'AI 通过 MCP 协议调用这里的工具。每次请求会显示为一条工作流，你可以在「工作流」页实时看到它的每一步和下载进度。所有接入方式都需要访问令牌；stdio 桥会自动读取本机令牌。',
    'connect.token': '访问令牌', 'connect.reveal': '显示', 'connect.hide': '隐藏', 'connect.regen': '更换令牌', 'connect.regenConfirm': '更换后，已接入的 HTTP 客户端需要更新令牌。继续？',
    'connect.tools': '可用工具', 'connect.nTools': '{n} 个工具', 'connect.ro': '只读', 'connect.task': '任务', 'connect.try': '试一试', 'connect.tryDesc': '接入后，对 AI 说：',
    'connect.tryText': '用 tg-agent 看看 @telegram 频道最近有哪些视频，挑两个最小的下载', 'connect.ccHttp': 'HTTP 方式（推荐），在终端运行：', 'connect.ccStdio': '或者 stdio 方式：',
    'connect.codex': '编辑 ~/.codex/config.toml，加入：', 'connect.json': '在客户端的 MCP 配置（mcpServers）中加入：', 'connect.http': '支持 Streamable HTTP 的客户端：', 'connect.other': 'ZCode / Cursor / 其他',
    'connect.copied': '已复制', 'connect.regened': '令牌已更换',
    'set.general': '通用', 'set.generalDesc': '界面与 AI 可见消息的语言。', 'set.language': '语言', 'set.download': '下载', 'set.downloadDesc': '文件保存位置、命名方式与并发。',
    'set.dir': '下载目录', 'set.template': '文件命名模板', 'set.templateHint': '可用 {chat} {chat_id} {msg_id} {name} {date}，用 / 分隔子目录', 'set.files': '同时下载文件数', 'set.conns': '每个文件的连接数', 'set.part': '分片大小 (KB)',
    'set.note': '并发越高越容易触发 Telegram 限流（FloodWait）。建议从 2 个文件 × 4 个连接开始；如果代理本身限速，加连接也不会更快。',
    'set.ai': 'AI 安全', 'set.aiDesc': 'AI 发起的大批量下载需要你在控制台批准；0 表示不限制。', 'set.apSize': '超过多少 GB 需批准', 'set.apFiles': '超过多少个文件需批准', 'set.idle': '未命名工作流空闲多久后结束（分钟）',
    'set.wait': '批量读取间隔（秒）', 'set.waitHint': '每读取约 100 条消息之间的等待，降低风控风险', 'set.proxy': '默认代理', 'set.proxyDesc': '新账号默认使用；每个账号也可单独设置。',
    'set.ptype': '类型', 'set.direct': '直连', 'set.host': '主机', 'set.port': '端口', 'set.save': '保存设置', 'set.saved': '设置已保存',
    'login.title': '需要访问令牌', 'login.desc': '为防止本机其他程序使用你的 Telegram 账号，控制台需要令牌。请使用启动窗口中打印的链接打开，或运行 tg-agent token 获取令牌后粘贴到这里。', 'login.ph': '访问令牌', 'login.go': '解锁', 'login.bad': '令牌不正确',
    'who.system': '系统', 'who.console': '控制台', 'who.download': '下载', 'who.export': '导出', 'who.index': '索引',
    'common.cancel': '取消', 'common.close': '关闭', 'common.unknown': '未知', 'common.ago': '前', 'common.none': '无',
    'kpi.idle': '空闲',
  },
  en: {
    'nav.section': 'Workspace', 'page.workflow': 'Workflows', 'page.browse': 'Browse', 'page.library': 'Library', 'page.tasks': 'Tasks',
    'page.watches': 'Watches', 'page.accounts': 'Accounts', 'page.connect': 'Connect AI', 'page.settings': 'Settings',
    'conn.ok': 'Service running', 'conn.bad': 'Service offline',
    'wf.flows': 'Workflows', 'wf.log': 'Log', 'wf.search': 'Search workflows', 'wf.follow': 'Follow the latest activity',
    'wf.active': 'In progress', 'wf.today': 'Today', 'wf.earlier': 'Earlier', 'wf.untitled': 'Untitled workflow', 'wf.none': 'No workflows yet. Once an AI is connected, each of its requests shows up here.',
    'wf.pick': 'Pick a workflow on the left', 'wf.steps': '{n} steps', 'wf.polls': 'Progress checked ×{n}', 'wf.waiting': 'Waiting for the AI’s next step…',
    'wf.finished': 'Finished', 'wf.failedEnd': 'Ended (failed)', 'wf.idleEnd': 'Ended', 'wf.implicitTip': 'The AI did not call tg_start_workflow, so these calls were grouped into an untitled workflow',
    'wf.delete': 'Delete', 'wf.deleteConfirm': 'Delete this workflow record?', 'wf.started': 'Started', 'wf.duration': 'Duration', 'wf.noSteps': 'No steps yet',
    'wf.args': 'Arguments', 'wf.result': 'Result', 'wf.error': 'Error', 'wf.tasks': 'Tasks', 'wf.step': 'Step', 'wf.more': '{n} more',
    'wf.renameHint': 'Click the title to rename', 'log.empty': 'Nothing logged yet',
    'status.active': 'Active', 'status.done': 'Done', 'status.failed': 'Failed', 'status.idle': 'Ended', 'status.canceled': 'Canceled', 'status.running': 'Running', 'status.error': 'Error',
    'ap.title': '{agent} wants to download {n} files ({size})', 'ap.approve': 'Approve', 'ap.reject': 'Reject', 'ap.node': 'Waiting for your approval: {n} files · {size}',
    'ap.watch': '{agent} created a watch: {chat}', 'ap.done': 'Approved', 'ap.rejected': 'Rejected',
    'task.approval': 'Needs approval', 'task.queued': 'Queued', 'task.running': 'Downloading', 'task.paused': 'Paused', 'task.done': 'Done', 'task.failed': 'Failed', 'task.canceled': 'Canceled', 'task.skipped': 'Exists',
    'tasks.active': 'Active', 'tasks.paused': 'Paused', 'tasks.done': 'Done', 'tasks.failed': 'Failed', 'tasks.jobs': 'Exports & index', 'tasks.all': 'All',
    'tasks.pauseAll': 'Pause all', 'tasks.resumeAll': 'Resume all', 'tasks.retryFailed': 'Retry failed', 'tasks.openDir': 'Downloads folder', 'tasks.none': 'No matching tasks',
    'tasks.scanned': '{n} scanned', 'tasks.handled': '{n} task(s) updated',
    'act.pause': 'Pause', 'act.resume': 'Resume', 'act.retry': 'Retry', 'act.open': 'Show in folder', 'act.cancel': 'Cancel', 'act.remove': 'Remove from list',
    'browse.searchDialogs': 'Search joined chats', 'browse.open': '@username or t.me link, press Enter', 'browse.all': 'All', 'browse.channels': 'Channels', 'browse.groups': 'Groups', 'browse.users': 'Private',
    'browse.pick': 'Pick a chat on the left, or enter a public channel’s username / link', 'browse.noAccount': 'No usable account — log in on the Accounts page', 'browse.loading': 'Loading…', 'browse.none': 'No results',
    'browse.files': 'Files', 'browse.msgs': 'Messages', 'browse.export': 'Export', 'browse.index': 'Index', 'browse.openTg': 'Open', 'browse.nameHas': 'Name contains', 'browse.ext': 'Extension',
    'browse.filter': 'Filter', 'browse.loaded': '{n} files loaded', 'browse.total': '{s} total', 'browse.scanned': '{n} messages scanned', 'browse.more': 'more available', 'browse.end': 'end reached',
    'browse.loadMore': 'Load more', 'browse.noFiles': 'No matching files', 'browse.noMsgs': 'No messages', 'browse.selAll': 'Select loaded', 'browse.dlSel': 'Download selected', 'browse.selHint': 'Tick files to download them together',
    'browse.selected': '{n} selected · {s}', 'browse.private': 'private', 'browse.members': '{n} members', 'browse.latest': 'latest #{n}', 'browse.notJoined': 'Not joined',
    'browse.queued': 'Queued {n} file(s), {s}', 'browse.skipped': ' ({n} skipped)', 'browse.pickFirst': 'Select some files first',
    'col.name': 'Name', 'col.size': 'Size', 'col.date': 'Date', 'col.msg': 'Msg', 'col.chat': 'Chat',
    'type.channel': 'Channel', 'type.supergroup': 'Supergroup', 'type.group': 'Group', 'type.user': 'User', 'type.bot': 'Bot',
    'kind.document': 'Docs', 'kind.video': 'Video', 'kind.audio': 'Audio', 'kind.photo': 'Photos', 'kind.voice': 'Voice',
    'exp.title': 'Export {t}', 'exp.desc': 'Scans the whole chat in the background and writes a file — good for large channels.', 'exp.what': 'Content', 'exp.files': 'File list', 'exp.msgs': 'Messages',
    'exp.format': 'Format', 'exp.limit': 'Max rows (empty = all)', 'exp.start': 'Start export', 'exp.started': 'Export started',
    'lib.searchPh': 'Search file names and captions in the local index (no Telegram requests)', 'lib.search': 'Search', 'lib.indexed': 'Indexed chats', 'lib.indexChat': 'Index a chat',
    'lib.compare': 'Compare two chats', 'lib.allChats': 'All chats', 'lib.sortDate': 'Newest', 'lib.sortSize': 'Largest', 'lib.sortName': 'Name', 'lib.matched': '{n} matches · {s}',
    'lib.noIndex': 'Nothing indexed yet. Browsing, listing files or “Index a chat” all add files to the local index.', 'lib.full': 'full', 'lib.partial': 'partial', 'lib.update': 'Update',
    'lib.files': '{n} files', 'lib.cmpA': 'Chat A', 'lib.cmpB': 'Chat B', 'lib.cmpBy': 'Match by', 'lib.byName': 'File name', 'lib.byNameSize': 'Name + size', 'lib.byStem': 'Name without extension/punctuation', 'lib.byFile': 'Same Telegram file',
    'lib.run': 'Compare', 'lib.both': 'In both', 'lib.onlyA': 'Only in A', 'lib.onlyB': 'Only in B', 'lib.idxTitle': 'Index a chat', 'lib.idxDesc': 'Scans every file of the chat in the background into the local index; searching and comparing then need no Telegram requests. Re-indexing only scans new messages.',
    'lib.full2': 'Rescan from the beginning', 'lib.idxStart': 'Start indexing', 'lib.idxStarted': 'Indexing started', 'lib.needTwo': 'Needs at least two indexed chats', 'lib.empty': 'Type keywords or set filters, then search',
    'watch.title': 'Watch chats', 'watch.intro': 'Checks chats on a schedule and queues new matching files automatically. Watches created by an AI stay off until you approve them.', 'watch.add': 'New watch',
    'watch.none': 'No watches yet', 'watch.pending': 'Needs approval', 'watch.every': 'every {n} min', 'watch.last': 'Last check', 'watch.never': 'never', 'watch.got': 'Downloaded', 'watch.from': 'Created by',
    'watch.check': 'Check now', 'watch.approve': 'Approve & enable', 'watch.filter': 'Filter', 'watch.any': 'all files', 'watch.interval': 'Interval (minutes)', 'watch.recent': 'Also check the last N messages',
    'watch.subdir': 'Sub-folder', 'watch.chat': 'Chat', 'watch.account': 'Account', 'watch.create': 'Create', 'watch.removeConfirm': 'Delete this watch?', 'watch.found': '{n} new file(s) found',
    'acc.add': 'Add account', 'acc.addDesc': 'Get api_id and api_hash at my.telegram.org → API development tools. api_hash is stored encrypted.',
    'acc.name': 'Display name', 'acc.phone': 'Phone (international format; optional for QR login)', 'acc.addGo': 'Add & connect', 'acc.edit': 'Edit', 'acc.remove': 'Remove', 'acc.default': 'default', 'acc.setDefault': 'Make default',
    'acc.id': 'Account ID', 'acc.phoneL': 'Phone', 'acc.proxy': 'Proxy', 'acc.follow': '(default)', 'acc.uid': 'User ID', 'acc.direct': 'direct',
    'acc.needLogin': 'Not logged in yet. Choose how to log in:', 'acc.qrLogin': 'QR code', 'acc.codeLogin': 'Login code', 'acc.enterCode': 'Enter the code you received', 'acc.code': 'Code', 'acc.login': 'Log in', 'acc.resend': 'Resend',
    'acc.need2fa': 'Two-step verification is on. Enter the password (not stored).', 'acc.password': '2FA password', 'acc.confirm': 'Confirm', 'acc.reconnect': 'Reconnect', 'acc.connecting': 'Connecting…',
    'acc.qrScan': 'Scan with Telegram on your phone: Settings → Devices → Link Desktop Device', 'acc.qrExpire': 'refreshes in {n}s', 'acc.cancel': 'Cancel',
    'acc.removeT': 'Remove account {n}?', 'acc.removeD': 'Deletes the locally stored session. Tick the box to also log the session out on Telegram’s servers.', 'acc.logout': 'Also log out this session on Telegram',
    'acc.saved': 'Saved', 'acc.added': 'Account added, connecting…', 'acc.codeSent': 'Code sent', 'acc.loggedIn': 'Logged in', 'acc.noPhone': 'No phone number — use QR login or add a phone in Edit',
    'acc.hashKeep': 'leave empty to keep', 'acc.ptype': 'Proxy', 'acc.pfollow': 'Use default', 'acc.none': 'No account',
    'st.ready': 'Ready', 'st.connecting': 'Connecting', 'st.need_login': 'Login needed', 'st.code_sent': 'Code sent', 'st.password_needed': '2FA needed', 'st.qr_waiting': 'Waiting for scan', 'st.error': 'Error', 'st.disconnected': 'Offline',
    'connect.title': 'Connect TG Agent to your AI tools', 'connect.intro': 'AIs call the tools here over MCP. Each request becomes a workflow, and you can watch every step and download live on the Workflows page. All connections need the access token; the stdio bridge reads it automatically on this machine.',
    'connect.token': 'Access token', 'connect.reveal': 'Show', 'connect.hide': 'Hide', 'connect.regen': 'Regenerate', 'connect.regenConfirm': 'HTTP clients that are already connected will need the new token. Continue?',
    'connect.tools': 'Tools', 'connect.nTools': '{n} tools', 'connect.ro': 'read-only', 'connect.task': 'task', 'connect.try': 'Try it', 'connect.tryDesc': 'Once connected, ask your AI:',
    'connect.tryText': 'Use tg-agent to see which videos @telegram posted recently and download the two smallest', 'connect.ccHttp': 'HTTP (recommended) — run in a terminal:', 'connect.ccStdio': 'or stdio:',
    'connect.codex': 'Add to ~/.codex/config.toml:', 'connect.json': 'Add to the client’s MCP config (mcpServers):', 'connect.http': 'Clients that support Streamable HTTP:', 'connect.other': 'ZCode / Cursor / others',
    'connect.copied': 'Copied', 'connect.regened': 'Token regenerated',
    'set.general': 'General', 'set.generalDesc': 'Language of the console and of messages shown to the AI.', 'set.language': 'Language', 'set.download': 'Downloads', 'set.downloadDesc': 'Where files go, how they are named, and concurrency.',
    'set.dir': 'Download folder', 'set.template': 'File name template', 'set.templateHint': 'Use {chat} {chat_id} {msg_id} {name} {date}; / creates sub-folders', 'set.files': 'Parallel files', 'set.conns': 'Connections per file', 'set.part': 'Part size (KB)',
    'set.note': 'More concurrency makes Telegram rate limits (FloodWait) more likely. Start with 2 files × 4 connections; if your proxy is the bottleneck, more connections won’t help.',
    'set.ai': 'AI safeguards', 'set.aiDesc': 'Large downloads started by an AI wait for your approval in the console. 0 = no limit.', 'set.apSize': 'Ask above (GB)', 'set.apFiles': 'Ask above (files)', 'set.idle': 'End untitled workflows after idle (min)',
    'set.wait': 'Delay between history batches (s)', 'set.waitHint': 'Pause after every ~100 messages read, to stay clear of rate limits', 'set.proxy': 'Default proxy', 'set.proxyDesc': 'Used by new accounts; each account can override it.',
    'set.ptype': 'Type', 'set.direct': 'Direct', 'set.host': 'Host', 'set.port': 'Port', 'set.save': 'Save', 'set.saved': 'Settings saved',
    'login.title': 'Access token required', 'login.desc': 'So that other programs on this computer can’t use your Telegram account, the console needs the token. Open the link printed in the TG Agent window, or run “tg-agent token” and paste it here.', 'login.ph': 'access token', 'login.go': 'Unlock', 'login.bad': 'Wrong token',
    'who.system': 'system', 'who.console': 'console', 'who.download': 'download', 'who.export': 'export', 'who.index': 'index',
    'common.cancel': 'Cancel', 'common.close': 'Close', 'common.unknown': 'unknown', 'common.ago': 'ago', 'common.none': 'none',
    'kpi.idle': 'idle',
  },
};
let LANG = 'en';
function t(key, vars) {
  let s = (I18N[LANG] && I18N[LANG][key]) ?? I18N.en[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  return s;
}
function applyI18n(root = document) {
  document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : 'en';
  root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  $$('#lang-switch button').forEach(b => b.classList.toggle('on', b.dataset.lang === LANG));
}

/* ------------------------------------------------------------ helpers */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function size(n) {
  n = Number(n) || 0;
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return i === 0 ? `${n} B` : `${n.toFixed(n >= 100 ? 0 : n >= 10 ? 1 : 2)} ${u[i]}`;
}
function dur(s) {
  if (s == null || !isFinite(s)) return '';
  s = Math.max(0, Math.round(s));
  const zh = LANG === 'zh';
  if (s < 60) return zh ? `${s} 秒` : `${s}s`;
  if (s < 3600) return zh ? `${Math.floor(s / 60)} 分 ${s % 60} 秒` : `${Math.floor(s / 60)}m ${s % 60}s`;
  if (s < 86400) return zh ? `${Math.floor(s / 3600)} 小时 ${Math.floor(s % 3600 / 60)} 分` : `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}m`;
  return zh ? `${Math.floor(s / 86400)} 天 ${Math.floor(s % 86400 / 3600)} 小时` : `${Math.floor(s / 86400)}d ${Math.floor(s % 86400 / 3600)}h`;
}
const ms = v => v == null ? '' : v < 1000 ? `${v}ms` : `${(v / 1000).toFixed(1)}s`;
function clock(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const hm = d.toLocaleTimeString(LANG === 'zh' ? 'zh-CN' : 'en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  return d.toDateString() === now.toDateString() ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm.slice(0, 5)}`;
}
function ago(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return LANG === 'zh' ? '刚刚' : 'just now';
  if (s < 3600) return LANG === 'zh' ? `${Math.floor(s / 60)} 分钟前` : `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return LANG === 'zh' ? `${Math.floor(s / 3600)} 小时前` : `${Math.floor(s / 3600)}h ago`;
  return clock(ts);
}
function dateStr(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function hue(s) {
  let h = 0;
  for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % 360;
}
const avatar = (title, cls = '') => `<div class="avatar ${cls}" style="--h:${hue(title)}">${esc((title || '?').trim().slice(0, 1).toUpperCase())}</div>`;
function who(source) {
  const base = String(source || '');
  const label = I18N[LANG]['who.' + base] ? t('who.' + base) : base;
  return `<span class="who" style="--h:${hue(base)}">${esc(label)}</span>`;
}
const KIND_ICON = { video: 'video', audio: 'audio', photo: 'photo', voice: 'mic', round: 'video', gif: 'photo', document: 'file', sticker: 'photo' };
const kindIco = k => `<span class="kind-ico kind-${esc(k)}">${icon(KIND_ICON[k] || 'file')}</span>`;
const TASK_TAG = { approval: 'info', queued: 'info', running: 'info', paused: 'warn', done: 'ok', failed: 'err', canceled: '', skipped: 'ok' };
const taskTag = s => `<span class="tag ${TASK_TAG[s] ?? ''}">${t('task.' + s)}</span>`;
const ST_TAG = { ready: 'ok', connecting: 'info', need_login: 'warn', code_sent: 'warn', password_needed: 'warn', qr_waiting: 'warn', error: 'err', disconnected: '' };
const statusTag = s => `<span class="tag ${ST_TAG[s] ?? ''}">${t('st.' + s)}</span>`;
const WF_TAG = { active: 'info', done: 'ok', failed: 'err', idle: '', canceled: '' };
const wfTag = s => `<span class="tag ${WF_TAG[s] ?? ''}">${t('status.' + s)}</span>`;
const pct = tk => tk.total ? Math.min(100, tk.done / tk.total * 100) : (tk.status === 'done' ? 100 : 0);

function toast(msg, ok = true) {
  const el = document.createElement('div');
  el.className = `toast ${ok ? 'ok' : 'err'}`;
  el.innerHTML = icon(ok ? 'check' : 'alert') + `<span>${esc(msg)}</span>`;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), ok ? 3000 : 6000);
}

/* ------------------------------------------------------------ API */
async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: { 'X-TGA': '1' }, credentials: 'same-origin' };
  if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers['Content-Type'] = 'application/json'; }
  const r = await fetch(path, init);
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && path !== '/api/login') { showLogin(); throw new Error(t('login.title')); }
  if (!r.ok) throw new Error(data.detail || data.error || `HTTP ${r.status}`);
  return data;
}
const post = (p, body = {}) => api(p, { method: 'POST', body });
async function tool(name, args) {
  const r = await post(`/api/tools/${name}`, args);
  if (!r.ok) throw new Error(r.error);
  return r.result;
}
function showLogin() { $('#login-screen').classList.add('show'); setTimeout(() => $('#login-token').focus(), 50); }

/* ------------------------------------------------------------ modal */
function openModal(html, onSubmit) {
  $('#modal').innerHTML = html;
  $('#modal-back').classList.add('show');
  const form = $('#modal form');
  form?.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = form.querySelector('[type=submit]');
    btn.disabled = true;
    try { await onSubmit(new FormData(form)); closeModal(); } catch (err) { toast(err.message, false); } finally { btn.disabled = false; }
  });
  $$('#modal [data-close]').forEach(b => b.onclick = closeModal);
  setTimeout(() => $('#modal input:not([type=checkbox])')?.focus(), 50);
}
function closeModal() { $('#modal-back').classList.remove('show'); }
function confirmBox(text) { return window.confirm(text); }

/* ------------------------------------------------------------ state */
const S = {
  accounts: [], settings: {}, stats: {}, tasks: new Map(), activity: new Map(), paths: {}, port: 17865,
  workflows: new Map(), watches: [], approvals: [], toolsMeta: {}, token: '', tokenShown: false,
  page: 'workflow', taskFilter: 'active', speedHist: Array(60).fill(0),
  wf: { sel: null, data: null, view: 'flows', q: '', follow: true, node: null, nodeData: null, newIds: new Set() },
  b: { account: '', kind: 'all', q: '', dialogs: [], chat: null, info: null, tab: 'files', files: [], fileCursor: null,
       fileSummary: null, msgs: [], msgCursor: null, selected: new Set(), f: { types: [], name: '', ext: '', min: '', max: '' }, loading: false },
  lib: { q: '', types: [], ext: '', min: '', max: '', sort: 'date', chat: '', results: null, index: [], cmp: null },
  qr: {},
};
const toolTitle = name => { const m = S.toolsMeta[name]; return m ? (LANG === 'zh' ? m.title_zh : m.title_en) : name; };
