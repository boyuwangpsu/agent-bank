"""Tests for the MCP Server tool handlers."""

import json

import pytest

import agent_bank.server as server
from agent_bank.markdown_store import MarkdownMemoryStore
from agent_bank.models import Memory


@pytest.fixture
def patched_store(tmp_path, monkeypatch):
    store = MarkdownMemoryStore(tmp_path / "memory")
    monkeypatch.setattr(server, "_get_store", lambda: store)
    monkeypatch.setattr(server, "detect_project", lambda: "agent-bank")
    return store


@pytest.mark.asyncio
async def test_remember_valid_content_stores_memory(patched_store):
    result = await server.call_tool(
        "remember",
        {
            "content": "潘总偏好 ROI 分析",
            "category": "people",
            "subject": "潘总",
            "tags": ["leader"],
        },
    )
    payload = json.loads(result[0].text)

    assert payload["status"] == "remembered"
    assert payload["category"] == "people"
    stored = patched_store.get(payload["id"])
    assert stored is not None
    assert stored.content == "潘总偏好 ROI 分析"
    assert stored.project == "agent-bank"
    assert (patched_store.root / "people" / "pan-zong.md").exists()
    assert (patched_store.root / "MEMORY_MAP.md").exists()


@pytest.mark.asyncio
async def test_remember_rejects_empty_content(patched_store):
    result = await server.call_tool("remember", {"content": "  \t\n"})
    payload = json.loads(result[0].text)

    assert "error" in payload
    assert "content" in payload["error"]
    assert patched_store.count().get("total") == 0


@pytest.mark.asyncio
async def test_remember_rejects_invalid_category(patched_store):
    result = await server.call_tool(
        "remember", {"content": "test", "category": "invalid"}
    )
    payload = json.loads(result[0].text)

    assert "error" in payload
    assert "category" in payload["error"]


@pytest.mark.asyncio
async def test_recall_returns_matching_results_and_touches_memory(patched_store):
    memory = patched_store.add(
        Memory(
            content="AI 平台 POC 需要 ROI 分析",
            category="work",
            scope="project",
            project="agent-bank",
        )
    )

    result = await server.call_tool("recall", {"query": "ROI", "category": "work"})
    payload = json.loads(result[0].text)

    assert payload["results"][0]["id"] == memory.id
    restored = patched_store.get(memory.id)
    assert restored is not None
    assert restored.access_count == 1
    assert restored.last_accessed is not None


@pytest.mark.asyncio
async def test_recall_empty_query_returns_error(patched_store):
    result = await server.call_tool("recall", {"query": ""})
    payload = json.loads(result[0].text)

    assert "error" in payload
    assert "query" in payload["error"]


@pytest.mark.asyncio
async def test_people_profile_context_forget_and_stats_handlers(patched_store):
    leader = patched_store.add(
        Memory(content="潘总偏好简洁", category="people", subject="潘总")
    )
    patched_store.add(Memory(content="我是负责人", category="identity"))
    patched_store.add(Memory(content="当前推进 AI POC", category="work", subject="AI POC"))

    people = json.loads((await server.call_tool("people", {"name": "潘总"}))[0].text)
    profile = json.loads((await server.call_tool("profile", {"section": "all"}))[0].text)
    context = json.loads((await server.call_tool("context", {"scope": "current"}))[0].text)
    stats = json.loads((await server.call_tool("stats", {}))[0].text)
    forgotten = json.loads(
        (await server.call_tool("forget", {"memory_id": leader.id}))[0].text
    )

    assert people["memories"][0]["content"] == "潘总偏好简洁"
    assert profile["identity"] == ["我是负责人"]
    assert context["work_context"][0]["subject"] == "AI POC"
    assert stats["memory_stats"]["total"] == 3
    assert forgotten["status"] == "forgotten"
    assert patched_store.get(leader.id) is None


@pytest.mark.asyncio
async def test_unknown_tool_returns_error_text(patched_store):
    result = await server.call_tool("unknown_tool", {})

    assert "未知工具" in result[0].text


@pytest.mark.asyncio
async def test_govern_tool_updates_fact_status(patched_store):
    memory = patched_store.add(
        Memory(content="潘总偏好 ROI 分析", category="people", subject="潘总")
    )

    result = await server.call_tool(
        "govern",
        {
            "memory_id": memory.id,
            "action": "confirm",
            "reason": "用户确认准确",
        },
    )
    payload = json.loads(result[0].text)

    assert payload["status"] == "governed"
    assert payload["fact"]["status"] == "confirmed"
    assert payload["fact"]["memory_id"] == memory.id


@pytest.mark.asyncio
async def test_govern_tool_returns_error_for_missing_target(patched_store):
    result = await server.call_tool("govern", {"action": "confirm"})
    payload = json.loads(result[0].text)

    assert "error" in payload
    assert "fact_id 或 memory_id" in payload["error"]


@pytest.mark.asyncio
async def test_merge_tool_creates_canonical_memory(patched_store):
    first = patched_store.add(
        Memory(content="潘总偏好简洁", category="people", subject="潘总")
    )
    second = patched_store.add(
        Memory(content="潘总要求 ROI 分析", category="people", subject="潘总")
    )

    result = await server.call_tool(
        "merge",
        {
            "memory_ids": [first.id, second.id],
            "content": "潘总偏好简洁，并要求 ROI 分析",
            "subject": "潘总",
            "reason": "合并重复事实",
        },
    )
    payload = json.loads(result[0].text)

    assert payload["status"] == "merged"
    assert payload["memory"]["content"] == "潘总偏好简洁，并要求 ROI 分析"
    assert payload["merged_from"] == [first.id, second.id]


@pytest.mark.asyncio
async def test_merge_tool_rejects_missing_inputs(patched_store):
    result = await server.call_tool("merge", {"memory_ids": [], "content": ""})
    payload = json.loads(result[0].text)

    assert "error" in payload
    assert "memory_ids" in payload["error"]


@pytest.mark.asyncio
async def test_merge_candidates_tool_returns_candidate_groups(patched_store):
    first = patched_store.add(
        Memory(content="潘总偏好简洁", category="people", subject="潘总")
    )
    second = patched_store.add(
        Memory(content="潘总要求 ROI 分析", category="people", subject="潘总")
    )

    result = await server.call_tool("merge_candidates", {})
    payload = json.loads(result[0].text)

    assert payload["candidates"] == [
        {
            "category": "people",
            "subject": "潘总",
            "count": 2,
            "memory_ids": [first.id, second.id],
            "contents": ["潘总偏好简洁", "潘总要求 ROI 分析"],
        }
    ]


@pytest.mark.asyncio
async def test_export_md_tool_writes_markdown_projection(patched_store, tmp_path, monkeypatch):
    patched_store.add(
        Memory(content="潘总偏好简洁", category="people", subject="潘总")
    )

    result = await server.call_tool("export_md", {})
    payload = json.loads(result[0].text)

    assert payload["status"] == "rebuilt"
    assert payload["path"] == str(patched_store.root / "MEMORY_MAP.md")
    assert (patched_store.root / "MEMORY_MAP.md").exists()
