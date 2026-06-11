"""MCP Server for agent-bank — workplace AI memory system.

Exposes tools for memory CRUD and resources for automatic steering injection.
"""

import asyncio
import json
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from agent_bank.config import (
    detect_project,
    get_dashboard_path,
    get_memory_root,
)
from agent_bank.markdown_store import MarkdownMemoryStore
from agent_bank.models import Memory, ValidationError, VALID_CATEGORIES, VALID_SCOPES, VALID_SOURCES
from agent_bank.steering import generate_steering
from agent_bank.visualize import write_dashboard

server = Server("agent-bank")

_store: MarkdownMemoryStore | None = None


def _get_store() -> MarkdownMemoryStore:
    global _store
    if _store is None:
        _store = MarkdownMemoryStore(get_memory_root())
    return _store


# ─── MCP Resources ───────────────────────────────────────────────────────────


@server.list_resources()
async def list_resources() -> list[Resource]:
    """Expose auto-generated steering as a resource.

    This is the core mechanism for "memory drives behavior":
    the Agent reads this resource and follows the rules inside.
    """
    return [
        Resource(
            uri="agent-bank://steering",
            name="agent-bank 行为规则",
            description="基于用户记忆自动生成的行为规则。Agent 应遵循这些规则来适配用户偏好和领导风格。",
            mimeType="text/markdown",
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Return the auto-generated steering content."""
    if uri == "agent-bank://steering":
        store = _get_store()
        return generate_steering(store)
    raise ValueError(f"Unknown resource: {uri}")


# ─── MCP Tools ────────────────────────────────────────────────────────────────


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="remember",
            description="存入一条记忆。Agent 在对话中发现用户偏好、领导要求、工作变化时自动调用。",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "要记住的内容",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(VALID_CATEGORIES),
                        "default": "preference",
                        "description": "记忆类型：identity(身份)/people(人际)/work(工作)/knowledge(知识)/preference(偏好)",
                    },
                    "subject": {
                        "type": "string",
                        "description": "记忆主体（如领导名字、项目名）",
                    },
                    "source": {
                        "type": "string",
                        "enum": list(VALID_SOURCES),
                        "default": "user_stated",
                        "description": "信息来源：user_stated(用户明确说的)/observed(观察到的)/inferred(推断的)",
                    },
                    "importance": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "重要性 0-1，不填则自动评估",
                    },
                    "scope": {
                        "type": "string",
                        "enum": list(VALID_SCOPES),
                        "default": "global",
                        "description": "可见范围：global(所有项目)/project(当前项目)/workspace(当前workspace)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签",
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="recall",
            description="检索与当前任务相关的记忆。Agent 在执行任务前自动调用。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询（关键词或自然语言描述）",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(VALID_CATEGORIES) + ["all"],
                        "default": "all",
                        "description": "按类型过滤",
                    },
                    "subject": {
                        "type": "string",
                        "description": "查询特定人/项目的记忆",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 10,
                        "description": "最多返回条数",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="people",
            description="查询人际网络中某人的完整信息：风格、偏好、汇报要求。",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "人名",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="profile",
            description="获取用户完整画像：身份、偏好、当前工作重点。",
            inputSchema={
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": ["identity", "preferences", "work", "all"],
                        "default": "all",
                    },
                },
            },
        ),
        Tool(
            name="context",
            description="获取当前工作上下文：在做什么项目、近期变化。",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["current", "all"],
                        "default": "current",
                    },
                },
            },
        ),
        Tool(
            name="forget",
            description="删除一条记忆。用户说'忘掉/不对'时调用。",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "要删除的记忆 ID",
                    },
                    "query": {
                        "type": "string",
                        "description": "模糊匹配要删除的记忆（与 memory_id 二选一）",
                    },
                },
            },
        ),
        Tool(
            name="govern",
            description="治理一条记忆事实：确认准确、废弃错误认知、标记过期。",
            inputSchema={
                "type": "object",
                "properties": {
                    "fact_id": {
                        "type": "string",
                        "description": "要治理的事实 ID（与 memory_id 二选一）",
                    },
                    "memory_id": {
                        "type": "string",
                        "description": "要治理的记忆 ID（与 fact_id 二选一）",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["confirm", "reject", "stale"],
                        "description": "治理动作：confirm(确认)/reject(废弃)/stale(过期)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "用户给出的治理原因",
                    },
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="merge",
            description="把多条重复或冲突记忆合并成一条新的当前认知，旧事实保留为历史证据。",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要合并的记忆 ID 列表，至少两条",
                    },
                    "content": {
                        "type": "string",
                        "description": "合并后的当前认知内容",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(VALID_CATEGORIES),
                        "description": "合并后记忆类型。不填则沿用第一条来源记忆。",
                    },
                    "subject": {
                        "type": "string",
                        "description": "合并后记忆主体。不填则沿用第一条来源记忆。",
                    },
                    "reason": {
                        "type": "string",
                        "description": "合并原因，会写入时间轴",
                    },
                },
                "required": ["memory_ids", "content"],
            },
        ),
        Tool(
            name="merge_candidates",
            description="推荐可能需要合并的重复记忆候选。只推荐，不自动合并。",
            inputSchema={
                "type": "object",
                "properties": {
                    "top_k": {
                        "type": "integer",
                        "default": 20,
                        "description": "最多返回候选组数量",
                    },
                },
            },
        ),
        Tool(
            name="stats",
            description="查看记忆统计：各类型数量、总数。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="visualize",
            description="生成本地记忆可视化页面：画像摘要、记忆图谱、时间轴演进。",
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["html"],
                        "default": "html",
                        "description": "输出格式。当前 MVP 支持 html。",
                    },
                },
            },
        ),
        Tool(
            name="export_md",
            description="把当前有效记忆导出为 Markdown 文件夹投影，便于 Kiro/Claude Code/Codex 读取。",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to handlers."""
    handlers = {
        "remember": _handle_remember,
        "recall": _handle_recall,
        "people": _handle_people,
        "profile": _handle_profile,
        "context": _handle_context,
        "forget": _handle_forget,
        "govern": _handle_govern,
        "merge": _handle_merge,
        "merge_candidates": _handle_merge_candidates,
        "stats": _handle_stats,
        "visualize": _handle_visualize,
        "export_md": _handle_export_md,
    }
    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"未知工具: {name}")]
    return await handler(arguments)


# ─── Tool Handlers ────────────────────────────────────────────────────────────


async def _handle_remember(args: dict) -> list[TextContent]:
    content = args.get("content", "").strip()
    if not content:
        return [_error("content 不能为空")]

    category = args.get("category", "preference")
    importance = args.get("importance")
    if importance is None:
        importance = _auto_importance(content, category)

    memory = Memory(
        content=content,
        category=category,
        scope=args.get("scope", "global"),
        subject=args.get("subject"),
        source=args.get("source", "user_stated"),
        importance=importance,
        tags=args.get("tags", []),
        project=detect_project(),
    )

    try:
        memory.validate()
    except ValidationError as e:
        return [_error(str(e))]

    store = _get_store()
    store.add(memory)

    return [_json({"status": "remembered", "id": memory.id, "category": category})]


async def _handle_recall(args: dict) -> list[TextContent]:
    query = args.get("query", "").strip()
    if not query:
        return [_error("query 不能为空")]

    db = _get_store()
    category = args.get("category", "all")
    category_filter = None if category == "all" else category

    results = db.search(
        query=query,
        category=category_filter,
        subject=args.get("subject"),
        project=detect_project(),
        top_k=args.get("top_k", 10),
    )

    # Update access tracking
    for mem in results:
        mem.touch()
        db.update(mem)

    output = [
        {
            "id": m.id,
            "content": m.content,
            "category": m.category,
            "subject": m.subject,
            "importance": m.importance,
            "updated_at": m.updated_at,
        }
        for m in results
    ]

    if not output:
        return [_json({"results": [], "message": "没有找到相关记忆"})]
    return [_json({"results": output})]


async def _handle_people(args: dict) -> list[TextContent]:
    name = args.get("name", "").strip()
    if not name:
        return [_error("name 不能为空")]

    db = _get_store()
    memories = db.search(query=name, category="people", subject=name, top_k=50)

    if not memories:
        # Try broader search
        memories = db.search(query=name, category="people", top_k=20)

    output = [{"content": m.content, "importance": m.importance} for m in memories]
    return [_json({"person": name, "memories": output})]


async def _handle_profile(args: dict) -> list[TextContent]:
    db = _get_store()
    section = args.get("section", "all")

    result: dict = {}
    if section in ("identity", "all"):
        identity = db.get_all(category="identity")
        result["identity"] = [m.content for m in identity]

    if section in ("preferences", "all"):
        prefs = db.get_all(category="preference")
        result["preferences"] = [m.content for m in prefs]

    if section in ("work", "all"):
        work = db.get_all(category="work")
        result["work"] = [
            {"content": m.content, "subject": m.subject} for m in work[:10]
        ]

    return [_json(result)]


async def _handle_context(args: dict) -> list[TextContent]:
    db = _get_store()
    work = db.get_all(category="work")
    # Sort by most recently updated
    work.sort(key=lambda m: m.updated_at, reverse=True)

    scope = args.get("scope", "current")
    if scope == "current":
        work = work[:10]

    output = [
        {"content": m.content, "subject": m.subject, "updated_at": m.updated_at}
        for m in work
    ]
    return [_json({"work_context": output})]


async def _handle_forget(args: dict) -> list[TextContent]:
    db = _get_store()
    memory_id = args.get("memory_id")
    query = args.get("query")

    if memory_id:
        success = db.delete(memory_id)
        if success:
            return [_json({"status": "forgotten", "id": memory_id})]
        return [_error(f"记忆 {memory_id} 不存在")]

    if query:
        # Find matching memories and delete them
        matches = db.search(query=query, top_k=5)
        if not matches:
            return [_error(f"没有找到匹配 '{query}' 的记忆")]
        deleted = []
        for m in matches:
            db.delete(m.id)
            deleted.append({"id": m.id, "content": m.content[:50]})
        return [_json({"status": "forgotten", "deleted": deleted})]

    return [_error("需要提供 memory_id 或 query")]


async def _handle_govern(args: dict) -> list[TextContent]:
    action = args.get("action")
    if action not in ("confirm", "reject", "stale"):
        return [_error("action 必须是 confirm/reject/stale 之一")]

    fact_id = args.get("fact_id")
    memory_id = args.get("memory_id")
    if not fact_id and not memory_id:
        return [_error("需要提供 fact_id 或 memory_id")]

    fact = _get_store().govern_fact(
        fact_id=fact_id,
        memory_id=memory_id,
        action=action,
        reason=args.get("reason", ""),
    )
    if fact is None:
        return [_error("没有找到可治理的记忆事实")]

    return [_json({"status": "governed", "action": action, "fact": fact})]


async def _handle_merge(args: dict) -> list[TextContent]:
    memory_ids = args.get("memory_ids")
    content = args.get("content", "")
    if not isinstance(memory_ids, list) or len(memory_ids) < 2:
        return [_error("memory_ids 至少需要两条记忆 ID")]
    if not isinstance(content, str) or not content.strip():
        return [_error("content 不能为空")]

    memory = _get_store().merge_memories(
        memory_ids=memory_ids,
        content=content,
        category=args.get("category"),
        subject=args.get("subject"),
        reason=args.get("reason", ""),
    )
    if memory is None:
        return [_error("合并失败：请检查 memory_ids 是否存在")]

    return [
        _json(
            {
                "status": "merged",
                "merged_from": memory_ids,
                "memory": memory.to_dict(),
            }
        )
    ]


async def _handle_merge_candidates(args: dict) -> list[TextContent]:
    top_k = args.get("top_k", 20)
    if not isinstance(top_k, int) or top_k < 1:
        return [_error("top_k 必须是正整数")]

    return [_json({"candidates": _get_store().merge_candidates(top_k=top_k)})]


async def _handle_stats(args: dict) -> list[TextContent]:
    db = _get_store()
    counts = db.count()
    return [_json({"memory_stats": counts})]


async def _handle_visualize(args: dict) -> list[TextContent]:
    output_format = args.get("format", "html")
    if output_format != "html":
        return [_error("visualize 当前只支持 html 格式")]

    db = _get_store()
    path = write_dashboard(db, get_dashboard_path())
    return [
        _json(
            {
                "status": "generated",
                "format": "html",
                "path": str(path),
                "message": "已生成本地记忆可视化页面",
            }
        )
    ]


async def _handle_export_md(args: dict) -> list[TextContent]:
    store = _get_store()
    path = store.rebuild_map()
    return [
        _json(
            {
                "status": "rebuilt",
                "format": "markdown",
                "path": str(path),
                "message": "已重建 Markdown 记忆地图",
            }
        )
    ]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _auto_importance(content: str, category: str) -> float:
    """Auto-evaluate importance based on content signals."""
    content_lower = content.lower()

    # High importance signals
    high_signals = ["记住", "以后", "总是", "每次", "永远", "不要再", "always", "never"]
    if any(s in content_lower for s in high_signals):
        return 0.9

    # Medium-high: leader preferences
    if category == "people":
        return 0.8

    # Medium-high: identity
    if category == "identity":
        return 0.8

    # Medium: work decisions
    decision_signals = ["决定", "选了", "用了", "不用", "方案"]
    if any(s in content_lower for s in decision_signals):
        return 0.7

    # Medium: preferences
    pref_signals = ["喜欢", "偏好", "习惯", "风格"]
    if any(s in content_lower for s in pref_signals):
        return 0.7

    # Lower: temporary context
    temp_signals = ["这周", "今天", "临时", "暂时"]
    if any(s in content_lower for s in temp_signals):
        return 0.4

    return 0.5


def _json(data: dict) -> TextContent:
    return TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))


def _error(msg: str) -> TextContent:
    return TextContent(type="text", text=json.dumps({"error": msg}, ensure_ascii=False))


# ─── Entry Point ──────────────────────────────────────────────────────────────


def main() -> None:
    """Start the MCP server via stdio transport."""
    asyncio.run(_run_server())


async def _run_server() -> None:
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    main()
