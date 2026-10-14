"""MCP server: direct mode (served by the main service at /mcp) and bridge mode (stdio → REST)."""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import mcp_types as types
from mcp.server import Server

from . import __version__

INSTRUCTIONS = """TG Agent gives you read-only access to the user's Telegram (channels, groups, chats) and fast file downloads.
The user watches every call live in the TG Agent web console, grouped into workflows.

Rules:
1. At the start of EVERY new user request call tg_start_workflow(title=...) with a short title in the user's language.
   When the request is done call tg_finish_workflow(summary=...).
2. After tg_download, call tg_wait_tasks instead of polling tg_tasks in a loop.
3. This is the user's real account: avoid unnecessary requests. Prefer tg_search_files / tg_compare_chats on the
   local index; use tg_index_chat or tg_export for complete listings of large chats.
4. Check count and total size with tg_plan_download before big downloads. Batches above the user's limit wait for approval
   in the console; tell the user when that happens.
5. When descriptions and files live in different chats, use tg_match_posts / tg_file_context(intro_chat=...).
6. When unsure (several versions, ambiguous matches), ask the user with tg_ask_user instead of guessing.
7. For long listings pass format="compact" (and fields=[...]) to save context. tg_search_archive and
   tg_search_files search locally without Telegram requests. Write useful findings into tg_notes.
8. The service never sends messages and never joins chats."""

ListFn = Callable[[], Awaitable[list[dict]]]
CallFn = Callable[[str, dict, str, str], Awaitable[tuple[bool, Any]]]


def client_name(ctx) -> str:
    try:
        return ctx.session.client_params.client_info.name or "agent"
    except Exception:
        return "agent"


def session_key(ctx) -> str:
    """Stable id of the client connection: the Streamable HTTP session header, else the session object."""
    req = getattr(ctx, "request", None)
    try:
        sid = req.headers.get("mcp-session-id") if req is not None else None
    except Exception:
        sid = None
    return f"mcp:{sid}" if sid else f"mcp:{id(ctx.session):x}"


def build_server(list_fn: ListFn, call_fn: CallFn, name: str = "tg-agent") -> Server:
    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        tools = []
        for t in await list_fn():
            tools.append(types.Tool(
                name=t["name"], title=t.get("title"), description=t["description"], input_schema=t["input_schema"],
                annotations=types.ToolAnnotations(title=t.get("title"), read_only_hint=t.get("read_only", True),
                                                  destructive_hint=False, open_world_hint=True),
            ))
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        from .workflow import progress_reporter
        token = progress_reporter.set(getattr(ctx.session, "report_progress", None))
        try:
            ok, result = await call_fn(params.name, params.arguments or {}, client_name(ctx), session_key(ctx))
        finally:
            progress_reporter.reset(token)
        text = json.dumps(result, ensure_ascii=False, indent=1, default=str) if ok else str(result)
        return types.CallToolResult(content=[types.TextContent(text=text)], is_error=not ok)

    async def on_list_prompts(ctx, params) -> types.ListPromptsResult:
        from . import recipes
        return types.ListPromptsResult(prompts=[
            types.Prompt(name=p["name"], title=p["title"], description=p["description"],
                         arguments=[types.PromptArgument(name=a["name"], description=a["description"], required=a["required"])
                                    for a in p["arguments"]])
            for p in recipes.prompts()])

    async def on_get_prompt(ctx, params: types.GetPromptRequestParams) -> types.GetPromptResult:
        from . import recipes
        text = recipes.render_prompt(params.name, params.arguments or {})
        return types.GetPromptResult(description=params.name, messages=[
            types.PromptMessage(role="user", content=types.TextContent(text=text))])

    return Server(name, version=__version__, title="TG Agent", instructions=INSTRUCTIONS,
                  on_list_tools=on_list_tools, on_call_tool=on_call_tool,
                  on_list_prompts=on_list_prompts, on_get_prompt=on_get_prompt)


def tool_dicts() -> list[dict]:
    from .tools import TOOLS
    return [{"name": t.name, "title": t.title_en, "title_zh": t.title_zh, "title_en": t.title_en,
             "description": t.description, "input_schema": t.input_schema(), "read_only": t.read_only} for t in TOOLS]


def build_direct_server() -> Server:
    from .tools import call_tool

    async def list_fn():
        return tool_dicts()

    async def call_fn(name, args, agent, session):
        return await call_tool(name, args, agent, session, transport="http")

    return build_server(list_fn, call_fn)
