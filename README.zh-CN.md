# TG Agent

**让 AI 读取 Telegram、下载文件，而且你能看着它干活。**

[English](README.md)

TG Agent 是一个本地服务，通过 [MCP](https://modelcontextprotocol.io) 让 **Claude Code、Codex、Cursor、ZCode** 等 AI 工具只读访问你的 Telegram 账号：公开频道、已加入的私有频道、群组和私聊。它能列出、搜索消息和文件，把见过的文件记入本地索引供离线查询，并用多连接并行的方式高速下载。

AI 做的每件事都会以 **工作流** 的形式实时显示在 Web 控制台：每个请求一张卡片，每次工具调用一个节点，箭头标出哪一步用了哪一步的结果，每个下载都有进度条。

- 🔍 **读取**：消息记录、搜索、按类型/文件名/扩展名/大小/日期筛选文件，查看邀请链接
- 🗂 **本地索引**：离线搜索、对比多个频道，不请求 Telegram
- ⚡ **高速下载**：每个文件多条 MTProto 连接，断点续传；并发数会根据 Telegram 限流自动调整
- 🗜 **分卷压缩包**：识别 `x.7z.001…`、`x.part1.rar` 等分卷，下载其中一卷会自动补齐整套，并标出缺失的卷
- ♻ **不重复下载**：已从其他频道下载过的同一文件会自动跳过
- ⏱ **限速与下载时段**、桌面通知、系统托盘图标（Windows）、新版本提醒
- 👁 **订阅**：自动下载频道里符合条件的新文件
- 🧭 **工作流**：AI 的每个请求按步骤画成流程图，可逐步查看参数和结果
- 🛡 **默认安全**：不发消息、不加群；AI 发起的大批量下载和 AI 创建的订阅需要你批准；本地访问令牌
- 👥 **多账号**，每个账号可单独设代理，支持扫码登录或验证码 + 两步验证
- 🌗 深色 / 浅色主题，克制的复古未来主义界面，中文 / English

## 快速开始

需要 Python 3.10+，以及你自己的 Telegram API 凭据（在 [my.telegram.org](https://my.telegram.org) → API development tools 获取 `api_id` / `api_hash`）。

- **Windows**：下载或克隆本仓库，双击 `start.bat`
- **macOS / Linux**：运行 `./start.sh`
- **pip / pipx**：`pipx install git+https://github.com/Creatfire/TelegramDownloadAgent`，然后运行 `tg-agent`
- 每个 [Release](https://github.com/Creatfire/TelegramDownloadAgent/releases) 附带打包好的 `tg-agent.exe`，无需安装 Python

首次启动会自动创建虚拟环境、安装依赖并打开控制台。然后：

1. **账号** → 添加账号 → 填 `api_id`、`api_hash`（手机号可选）→ 用 **扫码登录**（手机 Telegram：设置 → 设备 → 连接桌面设备）或验证码 + 两步验证密码登录。
2. **接入 AI** → 复制你所用工具的配置。
3. 对 AI 说：“用 tg-agent 看看 @telegram 频道最近有哪些视频，挑两个最小的下载”。

关闭 TG Agent 窗口即停止服务；登录状态会保留，未完成的下载下次启动自动续传。

## 接入 AI 工具

两种方式都需要服务在运行。控制台的「接入 AI」页会按你的实际路径和令牌生成配置，直接复制即可。

**Claude Code**（HTTP，推荐）

```bash
claude mcp add --transport http --scope user tg-agent http://127.0.0.1:17865/mcp --header "Authorization: Bearer <令牌>"
```

**Codex**：编辑 `~/.codex/config.toml`（stdio 桥会自动读取本机令牌）

```toml
[mcp_servers.tg-agent]
command = "E:\\path\\tg-agent\\.venv\\Scripts\\python.exe"
args = ["E:\\path\\tg-agent\\mcp_stdio.py"]
startup_timeout_sec = 20
tool_timeout_sec = 600
```

pip 安装时用 `command = "tg-agent-mcp"`；使用 exe 时为 `command = "...\\tg-agent.exe"`、`args = ["mcp"]`。

**Cursor / ZCode / 其他 `mcpServers` JSON 配置**：command/args 同上；支持 Streamable HTTP 的客户端可直接填：

```json
{ "url": "http://127.0.0.1:17865/mcp", "headers": { "Authorization": "Bearer <令牌>" } }
```

令牌可用 `tg-agent token` 查看，或在「接入 AI」页查看。

## 工具一览

| 工具 | 作用 |
|---|---|
| `tg_start_workflow` / `tg_finish_workflow` | 为当前请求开始 / 结束一条工作流（服务会要求 AI 每次都调用） |
| `tg_list_accounts` | 账号与登录状态 |
| `tg_list_dialogs` | 已加入的频道、群组、私聊（含私有频道） |
| `tg_resolve_chat` | 解析 @用户名、t.me 链接、私有频道链接或 ID；查看邀请链接但不加入 |
| `tg_get_messages` | 消息记录：分页、日期/ID 范围、关键字、仅媒体 |
| `tg_search_messages` | 在单个对话或全部已加入对话中搜索 |
| `tg_get_message` | 读取单条消息全文（含相册） |
| `tg_list_files` | 文件元数据、筛选、数量和总大小（同时写入本地索引） |
| `tg_export` | 后台导出全部文件清单或消息为 csv / json / jsonl / md |
| `tg_plan_download` | 下载预估：文件数、总大小、分卷套数与缺失卷、已下载过的文件、是否需要批准、预计耗时 |
| `tg_download` | 按链接、消息 ID 或筛选条件加入下载（默认自动补齐分卷） |
| `tg_wait_tasks` | 等待任务完成并推送进度，不再需要反复轮询 |
| `tg_tasks` / `tg_task_control` | 进度、速度、剩余时间、等待原因；暂停 / 继续 / 重试 / 取消 |
| `tg_index_chat` / `tg_index_status` | 把整个对话（增量）索引到本地 SQLite |
| `tg_search_files` | 跨对话搜索本地索引，不请求 Telegram |
| `tg_compare_chats` | 两个对话共有 / 独有的文件（按文件名、文件名+大小、去扩展名、同一文件） |
| `tg_watch` | 管理订阅（AI 创建的需批准） |

## 工作流视图

- **左栏**：按状态和日期分组的工作流，显示 AI 客户端、步数和时间。
- **中间**：选中工作流的步骤。细线连接相邻步骤，左侧琥珀色弧线表示 **数据依赖**（某一步用了前面某一步产出的频道、消息或任务）。下载步骤下方列出文件和实时进度。反复查询进度不会产生新节点，只显示“已查询进度 ×N”。
- **右栏**：点击节点查看完整参数和结果。
- 勾选“自动跟随最新活动”会自动跳到 AI 正在执行的工作流；「日志」标签显示原始事件流。
- 「导出报告」把工作流保存为 Markdown；「重跑」按原参数重新执行全部步骤（下载仍遵守批准规则）。

AI 没有调用 `tg_start_workflow` 时，调用仍会被记录，归入该会话的“未命名工作流”。

## 下载速度

每个文件通过多条 MTProto 连接并行下载（同 [tdl](https://github.com/iyear/tdl) 的思路），写入预分配的 `.part` 文件并记录已完成分片，暂停、重启、断线后都能续传。

Telegram 会限制单个账号的文件请求频率。设置里的并发数是**上限**（默认 2 个文件 × 每个 4 条连接）：一旦收到 FloodWait，TG Agent 会把同时进行的请求减半、等限流结束，再在平稳后逐步加回。任务会显示等待原因（“限流等待 37s”“重新连接中”“等待下载时段”），3 分钟没有进展的下载会自动换新连接。

可在设置中限制总速度（KB/s）和下载时段（如 23:00–07:00）。

**瓶颈通常在代理**：代理本身限速时，加连接也不会更快。可以试试 TUN 模式代理并在 TG Agent 里选“直连”，或换更快的代理。

## 安全与隐私

- 只读：不发消息、不点赞、不加入任何对话。
- 只监听 `127.0.0.1`，拒绝非本机 Host（防 DNS 重绑定），所有 API 和 MCP 请求都需要访问令牌；用 Cookie 认证的写操作还需要自定义请求头（防 CSRF）。
- AI 发起的超过限额的下载（默认 2 GB 或 50 个文件）和 AI 创建的订阅，需要你在控制台批准。
- `api_hash` 加密保存（Windows 用 DPAPI，macOS/Linux 用系统钥匙串）；两步验证密码从不保存。
- `data/sessions/*.session` **等同于你的登录状态**，切勿外传。移除账号时可选择同时在 Telegram 上注销会话。

通过任何第三方客户端使用账号都需遵守 [Telegram 服务条款](https://telegram.org/tos) 和 API 条款。大量自动化操作可能导致账号被限流或受限，使用风险由你自行承担。

## 数据位置

从源码目录运行（`start.bat` / `start.sh`）时数据放在代码旁边；pip 安装时放在 `~/.tg-agent`。可用 `TGA_DATA_DIR` 修改，端口（默认 `17865`）可用 `TGA_PORT` 修改。

| 路径 | 内容 |
|---|---|
| `data/accounts.json` | 账号（`api_hash` 已加密） |
| `data/sessions/` | Telegram 会话 |
| `data/tg-agent.db` | 工作流、本地文件索引、订阅 |
| `data/token` | 访问令牌 |
| `data/exports/` | 导出文件 |
| `downloads/` | 默认下载目录 |

## 开发与测试

见 [README.md 的 Development 部分](README.md#development)；人工 / AI 测试清单见 [docs/TESTING.md](docs/TESTING.md)。

## 致谢

基于 [Telethon](https://github.com/LonamiWebs/Telethon)。下载思路参考 [tdl](https://github.com/iyear/tdl)，订阅与筛选参考 [telegram_media_downloader](https://github.com/tangyoha/telegram_media_downloader)。

内置字体（SIL OFL 1.1，许可见 `tgagent/web/fonts/`）：[缝合像素字体 Fusion Pixel](https://github.com/TakWolf/fusion-pixel-font)（仅保留界面用到的字，可用 `tools/subset_fonts.py` 重新生成）、[VT323](https://fonts.google.com/specimen/VT323)、[Silkscreen](https://fonts.google.com/specimen/Silkscreen)。

## 许可证

[MIT](LICENSE)
