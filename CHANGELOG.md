# Changelog

## 1.2.0

### For AI agents
- `tg_match_posts` pairs description posts in an intro chat with files in a download chat (split archives grouped); `tg_file_context` reads a file's caption, nearby posts and album and extracts passwords, versions, links and sizes.
- Local **message archive** with full-text search (`tg_search_archive`): everything read or indexed is searchable offline.
- `tg_ask_user` asks the user in the console and waits; `tg_notes` keeps shared per-chat notes (also returned by `tg_resolve_chat`).
- **Recipes**: reusable workflows with parameters and references to earlier results; built-ins, save any workflow as a recipe, run on a schedule, and exposed as MCP prompts (slash commands). `tg_list_recipes`, `tg_run_recipe`.
- `tg_extract` tests or extracts archives with 7-Zip.
- `format="compact"` / `fields=[...]` on listing tools to save context.
- Per-AI daily request and download quotas, chat allow-lists and an off switch; a global Telegram request budget (requests per minute).

### Console
- New calm "warm graphite" light and dark themes; system fonts only.
- Workflows drawn as **swim lanes per chat**, plain-language steps, an auto-generated summary, orange states by strength (waiting / running / done), answers to AI questions inside the step, save-as-recipe.
- **Dashboard**: speed over 24 h, daily downloads, library make-up, top chats, calls per AI, tool timings (scatter), Telegram requests and rate limits.
- Recipes page (run, schedule), chat notes and file details (passwords) in Browse, message search in Library, Extract action on finished archives, per-AI limits in Settings.
- Assets are cache-busted per version.

## 1.1.0

### Downloads
- **Adaptive concurrency.** In-flight file requests are capped per account and halved whenever Telegram answers with FloodWait; all requests pause until the wait is over, and capacity is added back slowly while things are quiet. FloodWait no longer counts as a failed attempt.
- **Wait reasons.** Tasks show why they are not moving: *rate-limited N s*, *reconnecting*, *waiting for download hours*, *stalled, reconnected*.
- **Stall watchdog.** A download without progress for 3 minutes gets fresh connections and resumes from its `.part` file.
- **Split archives.** `x.7z.001`, `x.part1.rar`, `x.z01`, `x.001` volumes are recognised. Downloading one volume also queues the rest of the set (`complete_archives`, on by default); listings and the library show sets and missing volumes.
- **No duplicates.** A file already downloaded (same Telegram file, e.g. forwarded to several channels) is skipped; the library marks downloaded files.
- **Speed limit and download hours** (Settings).
- **Clear error when the download folder is unavailable** (e.g. an external drive is disconnected) instead of failing every task.

### For AI agents
- `tg_plan_download` — dry run with count, size, archive sets, duplicates, approval and estimated time.
- `tg_wait_tasks` — waits for tasks and sends MCP progress notifications (HTTP and stdio), replacing polling loops.
- Workflow **report export** (Markdown) and **re-run**.

### Console
- New look: warm charcoal / beige paper themes with better contrast, one burnt-orange accent, pixel headings, CRT-style numerals, LED-segment progress bars and CRT ripples on live indicators.
- Desktop notifications (downloads finished/failed, approvals, workflows finished), update notice, tray icon on Windows (open console, pause all, quit).
- Sizes and speeds below 1 KB show as `0 KB`; meaningless ETAs are hidden.

### Fixes
- Speeds decayed towards zero forever (`4.8e-21 B/s`) and produced absurd ETAs.
- Tool errors are now logged with a traceback.

## 1.0.0

First public release: MCP server (HTTP + stdio bridge), workflow view, local index, watches, approvals, QR login, access token, Chinese/English UI.
