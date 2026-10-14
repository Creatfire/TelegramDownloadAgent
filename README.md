# TG Agent

**Let your AI agent read Telegram and download files — and watch it work.**

[简体中文](README.zh-CN.md)

TG Agent is a local service that gives AI tools such as **Claude Code, Codex, Cursor and ZCode** read-only access to your Telegram account over [MCP](https://modelcontextprotocol.io): public channels, private channels you have joined, groups and chats. It can list and search messages and files, keep an offline index of everything it has seen, and download files fast over parallel connections.

Everything the AI does shows up live in a web console as a **workflow**: one card per request, one node per tool call, arrows showing which step used which result, and progress bars for every download.

- 🔍 **Read** — history, search, file listings with filters (kind, name, extension, size, date), invite-link inspection
- 🗂 **Local index** — search and compare channels offline, no Telegram requests
- ⚡ **Fast downloads** — several MTProto connections per file, resumable; concurrency adapts to Telegram's rate limits by itself
- 🗜 **Split archives** — `x.7z.001…`, `x.part1.rar`… are recognised; asking for one volume fetches the whole set and missing volumes are flagged
- ♻ **No duplicates** — a file already downloaded from another chat is skipped
- ⏱ **Speed limit and download hours**, desktop notifications, a tray icon (Windows) and an update check
- 👁 **Watches** — automatically download new matching files from a channel
- 🧭 **Workflows** — every AI request grouped and drawn as a step graph you can inspect
- 🛡 **Safe by default** — never sends messages or joins chats; large AI downloads and AI-created watches wait for your approval; local access token
- 👥 **Multiple accounts**, per-account proxies, QR-code or code + 2FA login
- 🌗 Dark / light theme with a restrained retro-futurist look, English / 中文

## Quick start

You need Python 3.10+ and your own Telegram API credentials (`api_id` / `api_hash` from [my.telegram.org](https://my.telegram.org) → *API development tools*).

**Windows** — download or clone this repository and double-click `start.bat`.
**macOS / Linux** — run `./start.sh`.
**Or with pip / pipx:**

```bash
pipx install git+https://github.com/Creatfire/TelegramDownloadAgent
tg-agent
```

A pre-built Windows `tg-agent.exe` is attached to each [release](https://github.com/Creatfire/TelegramDownloadAgent/releases).

The first start creates a virtual environment, installs dependencies and opens the console. Then:

1. **Accounts** → *Add account* → enter `api_id`, `api_hash` (phone is optional) → log in with a **QR code** (scan in Telegram: Settings → Devices → Link Desktop Device) or a login code + 2FA password.
2. **Connect AI** → copy the configuration for your tool (see below).
3. Ask your AI: *“Use tg-agent to see which videos @telegram posted recently and download the two smallest.”*

Closing the TG Agent window stops the service. Logins are kept and unfinished downloads resume on the next start.

## Connecting AI tools

Both transports need the service to be running. The console's **Connect AI** page generates these snippets with your real paths and token.

**Claude Code** (HTTP, recommended)

```bash
claude mcp add --transport http --scope user tg-agent http://127.0.0.1:17865/mcp --header "Authorization: Bearer <TOKEN>"
```

**Codex** — `~/.codex/config.toml` (stdio bridge; it reads the token automatically)

```toml
[mcp_servers.tg-agent]
command = "/path/to/tg-agent/.venv/bin/python"     # Windows: ...\\.venv\\Scripts\\python.exe
args = ["/path/to/tg-agent/mcp_stdio.py"]
startup_timeout_sec = 20
tool_timeout_sec = 600
```

If you installed with pip, use `command = "tg-agent-mcp"` and no args. With the exe: `command = "C:\\...\\tg-agent.exe"`, `args = ["mcp"]`.

**Cursor / ZCode / any `mcpServers` JSON config** — same command/args as above, or for clients with Streamable HTTP:

```json
{ "url": "http://127.0.0.1:17865/mcp", "headers": { "Authorization": "Bearer <TOKEN>" } }
```

Get the token with `tg-agent token` (or from the Connect AI page).

## Tools

| Tool | What it does |
|---|---|
| `tg_start_workflow` / `tg_finish_workflow` | Open / close a workflow for the current user request (the AI is instructed to always do this) |
| `tg_list_accounts` | Accounts and login status |
| `tg_list_dialogs` | Joined channels, groups, chats (including private channels) |
| `tg_resolve_chat` | Resolve @username, t.me link, private `t.me/c/…` link or id; inspect invite links without joining |
| `tg_get_messages` | History with paging, date/id range, keyword, media only |
| `tg_search_messages` | Search one chat or all joined chats |
| `tg_get_message` | One message in full, albums included |
| `tg_list_files` | File metadata with filters, counts and total size (also feeds the local index) |
| `tg_export` | Background export of all files or messages to csv / json / jsonl / md |
| `tg_plan_download` | Dry run: file count, total size, split-archive sets and missing volumes, already-downloaded files, approval needed, estimated time |
| `tg_download` | Queue downloads by links, by message ids, or by filter (completes split archives by default) |
| `tg_wait_tasks` | Wait for tasks to finish with progress notifications — no polling loops |
| `tg_tasks` / `tg_task_control` | Progress, speed, ETA, why a task is waiting; pause / resume / retry / cancel |
| `tg_index_chat` / `tg_index_status` | Index a whole chat (incrementally) into the local SQLite index |
| `tg_search_files` | Search the local index across chats — no Telegram requests |
| `tg_compare_chats` | What two chats have in common / only one has (by name, name+size, stem or identical file) |
| `tg_watch` | Manage watches (AI-created ones need approval) |

## The workflow view

- **Left:** workflows grouped by state and day; each shows the AI client, number of steps and time.
- **Middle:** the steps of the selected workflow. Thin lines link consecutive steps; amber arcs in the margin mark **data dependencies** (a step that used a chat, message or task produced by an earlier step). Download steps list their files with live progress. Repeated progress polling doesn't add nodes; it shows as *“Progress checked ×N”*.
- **Right:** click a node to see its full arguments and result.
- *Follow the latest activity* jumps to whatever the AI is doing now. The **Log** tab shows the raw event stream.
- **Export report** saves a workflow as Markdown; **Re-run** replays its steps as a new workflow (downloads still follow the approval rules).

If an AI doesn't call `tg_start_workflow`, its calls are still recorded, in an *untitled workflow* per session.

## Download speed

Each file is fetched over several MTProto connections in parallel (like [tdl](https://github.com/iyear/tdl)), written into a pre-allocated `.part` file, and finished parts are recorded so downloads survive pauses, restarts and dropped connections.

Telegram limits how many file requests an account may make. Settings give the *maximum* concurrency (default 2 files × 4 connections); TG Agent halves its in-flight requests whenever Telegram answers with FloodWait, pauses until the wait is over, and slowly adds capacity back while things are quiet. Tasks show why they are waiting (*rate-limited 37 s*, *reconnecting*, *waiting for download hours*), and a download that makes no progress for 3 minutes gets fresh connections automatically.

You can cap total speed (KB/s) and restrict downloads to certain hours (e.g. 23:00–07:00) in Settings.

**Your proxy is usually the bottleneck.** If it caps throughput, more connections won't help — try a TUN-mode proxy with *Direct* in TG Agent, or a faster proxy.

## Safety and privacy

- Read-only: TG Agent never sends messages, reacts, or joins chats.
- The service listens on `127.0.0.1` only, rejects foreign `Host` headers (DNS rebinding) and requires an access token on every API and MCP request. Cookie-authenticated writes also need a custom header (CSRF).
- AI-initiated downloads above your limits (default 2 GB or 50 files) and AI-created watches wait for approval in the console.
- `api_hash` is encrypted at rest (Windows DPAPI, or the system keychain on macOS/Linux). 2FA passwords are never stored.
- `data/sessions/*.session` **is your login** — never share it. Removing an account can also log the session out on Telegram.

Using your account through any third-party client is subject to [Telegram's Terms of Service](https://telegram.org/tos) and API terms. Heavy automated use can get an account rate-limited or restricted; you are responsible for how you use this tool.

## Data locations

Running from a checkout (`start.bat` / `start.sh`), everything lives next to the code; installed packages use `~/.tg-agent`. Override with `TGA_DATA_DIR`. The port (default `17865`) can be changed with `TGA_PORT`.

| Path | Contents |
|---|---|
| `data/accounts.json` | Accounts (encrypted `api_hash`) |
| `data/sessions/` | Telegram sessions |
| `data/tg-agent.db` | Workflows, local file index, watches |
| `data/token` | Access token |
| `data/exports/` | Exports |
| `downloads/` | Default download folder |

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest              # offline unit tests
.venv/bin/python -m tgagent             # run the service
.venv/bin/python tests/mcp_check.py     # MCP connectivity check (service must be running)
.venv/bin/python tests/workflow_demo.py # simulated agent session for the workflow view
```

```
tgagent/
  cli.py          entry point (tg-agent, tg-agent token, tg-agent mcp)
  server.py       FastAPI: REST, SSE, auth, console, embedded MCP (/mcp)
  mcp_server.py   MCP server definition;  mcp_stdio.py  stdio bridge
  tools.py        tool registry shared by MCP and the console
  workflow.py     sessions / workflows / steps and data-flow inference
  readers.py      read-only Telegram queries
  tasks.py        download queue, approvals, exports, index scans
  fastdl.py       parallel chunked downloader
  index.py        local SQLite file index;  watch.py  watches
  accounts.py     accounts, code / 2FA / QR login;  secure.py  secret storage
  web/            console (plain HTML/CSS/JS, no build step)
```

Manual test checklist for testers (human or AI): [docs/TESTING.md](docs/TESTING.md).

## Credits

Built on [Telethon](https://github.com/LonamiWebs/Telethon). Download approach inspired by [tdl](https://github.com/iyear/tdl); watch/filter ideas from [telegram_media_downloader](https://github.com/tangyoha/telegram_media_downloader).

Bundled fonts (SIL Open Font License 1.1, see `tgagent/web/fonts/`): [Fusion Pixel Font](https://github.com/TakWolf/fusion-pixel-font) (subset to the UI's characters — rebuild with `tools/subset_fonts.py`), [VT323](https://fonts.google.com/specimen/VT323), [Silkscreen](https://fonts.google.com/specimen/Silkscreen).

## License

[MIT](LICENSE)
