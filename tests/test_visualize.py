"""Tests for the memory visualization dashboard."""

import json
from pathlib import Path

import pytest

from agent_bank.markdown_store import MarkdownMemoryStore
from agent_bank.models import Memory
from agent_bank.visualize import render_dashboard_html, write_dashboard


def _seed_dashboard_memories(db: MarkdownMemoryStore) -> None:
    people = Memory(
        content="潘总偏好简洁、数据驱动、有 ROI 分析",
        category="people",
        subject="潘总",
        importance=0.9,
        tags=["leader", "roi"],
        created_at="2026-05-01T09:00:00",
        updated_at="2026-05-20T09:00:00",
    )
    people.update_content(
        "潘总偏好简洁、数据驱动、有 ROI 分析；材料需要明确下一步",
        reason="用户补充了最新汇报反馈",
    )
    people.updated_at = "2026-05-20T09:00:00"
    people.timeline[0]["date"] = "2026-05-20T09:00:00"
    db.add(people)
    db.add(
        Memory(
            content="我是数智发展部负责人，负责 AI 平台和数据平台推进",
            category="identity",
            importance=0.8,
            created_at="2026-05-01T08:00:00",
            updated_at="2026-05-01T08:00:00",
        )
    )
    db.add(
        Memory(
            content="当前在推进 AI 平台 POC，目标是验证降本增效",
            category="work",
            subject="AI 平台 POC",
            importance=0.8,
            created_at="2026-05-18T10:00:00",
            updated_at="2026-05-18T10:00:00",
        )
    )
    db.add(
        Memory(
            content="PPT 默认不超过 15 页，用中文，先结论后证据",
            category="preference",
            importance=0.7,
            created_at="2026-05-10T10:00:00",
            updated_at="2026-05-10T10:00:00",
        )
    )
    db.add(
        Memory(
            content="青冷指青岛中集冷藏箱，不是青龙",
            category="knowledge",
            subject="青冷",
            importance=0.6,
            created_at="2026-05-12T10:00:00",
            updated_at="2026-05-12T10:00:00",
        )
    )


def test_render_dashboard_prioritizes_profile_summary_and_memory_map(tmp_path: Path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    _seed_dashboard_memories(db)

    html = render_dashboard_html(db)

    assert "Agent 当前怎么理解我" in html
    assert "我是数智发展部负责人" in html
    assert "潘总" in html
    assert "AI 平台 POC" in html
    assert "PPT 默认不超过 15 页" in html
    assert "青冷" in html
    assert "记忆图谱" in html
    assert "关系：关键人" in html


def test_render_dashboard_includes_evolution_timeline(tmp_path: Path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    _seed_dashboard_memories(db)

    html = render_dashboard_html(db)

    assert "时间轴" in html
    assert "用户补充了最新汇报反馈" in html
    assert "材料需要明确下一步" in html
    assert "2026-05-20" in html
    assert "新增记忆" in html


def test_render_dashboard_shows_governed_fact_status(tmp_path: Path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    confirmed = db.add(
        Memory(content="潘总偏好 ROI 分析", category="people", subject="潘总")
    )
    rejected = db.add(Memory(content="错误工作上下文", category="work", subject="旧项目"))
    db.govern_fact(memory_id=confirmed.id, action="confirm", reason="用户确认准确")
    db.govern_fact(memory_id=rejected.id, action="reject", reason="用户标记错误")

    html = render_dashboard_html(db)

    assert "事实治理状态" in html
    assert "已确认" in html
    assert "已废弃" in html
    assert "用户确认准确" in html
    assert "用户标记错误" in html


def test_render_dashboard_shows_merged_fact_status(tmp_path: Path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    first = db.add(Memory(content="潘总偏好简洁", category="people", subject="潘总"))
    second = db.add(
        Memory(content="潘总要求 ROI 分析", category="people", subject="潘总")
    )
    db.merge_memories(
        memory_ids=[first.id, second.id],
        content="潘总偏好简洁，并要求 ROI 分析",
        subject="潘总",
        reason="合并重复事实",
    )

    html = render_dashboard_html(db)

    assert "已合并" in html
    assert "合并事实" in html
    assert "合并重复事实" in html


@pytest.mark.asyncio
async def test_write_dashboard_creates_html_file(tmp_path: Path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    _seed_dashboard_memories(db)
    output_path = tmp_path / "dashboard.html"

    written = write_dashboard(db, output_path)

    assert written == output_path
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("<!doctype html>")


@pytest.mark.asyncio
async def test_server_visualize_tool_returns_dashboard_path(tmp_path: Path, monkeypatch):
    import agent_bank.server as server

    db = MarkdownMemoryStore(tmp_path / "memory")
    _seed_dashboard_memories(db)
    output_path = tmp_path / "dashboard.html"
    monkeypatch.setattr(server, "_get_store", lambda: db)
    monkeypatch.setattr(server, "get_dashboard_path", lambda: output_path)

    result = await server.call_tool("visualize", {})
    payload = json.loads(result[0].text)

    assert payload["status"] == "generated"
    assert payload["path"] == str(output_path)
    assert output_path.exists()
