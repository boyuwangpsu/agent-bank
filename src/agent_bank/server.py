"""MCP Server for agent-bank — workplace AI memory system.

Exposes tools for memory CRUD and resources for automatic steering injection.
"""

import asyncio
import json
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from agent_bank.config import get_db_path, detect_project
from agent_bank.db import Database
from agent_bank.models import Memory, ValidationError, VALID_CATEGORIES, VALID_SCOPES, VALID_SOURCES
from agent_bank.steering import generate_steering

server = Server("agent-bank")

_db: Database | None = None


def _get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(get_db_path())
    return _db


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
        db = _get_db()
        return generate_steering(db)
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
            name="stats",
            description="查看记忆统计：各类型数量、总数。",
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
        "stats": _handle_stats,
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

    db = _get_db()
    db.add(memory)

    return [_json({"status": "remembered", "id": memory.id, "category": category})]


async def _handle_recall(args: dict) -> list[TextContent]:
    query = args.get("query", "").strip()
    if not query:
        return [_error("query 不能为空")]

    db = _get_db()
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

    db = _get_db()
    memories = db.search(query=name, category="people", subject=name, top_k=50)

    if not memories:
        # Try broader search
        memories = db.search(query=name, category="people", top_k=20)

    output = [{"content": m.content, "importance": m.importance} for m in memories]
    return [_json({"person": name, "memories": output})]


async def _handle_profile(args: dict) -> list[TextContent]:
    db = _get_db()
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
    db = _get_db()
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
    db = _get_db()
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


async def _handle_stats(args: dict) -> list[TextContent]:
    db = _get_db()
    counts = db.count()
    return [_json({"memory_stats": counts})]


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
