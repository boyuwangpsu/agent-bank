"""Tests for Markdown-backed memory search behavior."""

from agent_bank.markdown_store import MarkdownMemoryStore
from agent_bank.models import Memory


def _seed_search_memories(db: MarkdownMemoryStore) -> None:
    db.add(
        Memory(
            id="global-pref",
            content="PPT 默认不超过 15 页",
            category="preference",
            scope="global",
            tags=["ppt", "style"],
            importance=0.7,
        )
    )
    db.add(
        Memory(
            id="project-work",
            content="AI 平台 POC 需要 ROI 分析",
            category="work",
            scope="project",
            subject="AI 平台",
            project="agent-bank",
            tags=["roi"],
            importance=0.8,
        )
    )
    db.add(
        Memory(
            id="other-project",
            content="其他项目的 ROI 记忆",
            category="work",
            scope="project",
            project="other",
            importance=1.0,
        )
    )
    db.add(
        Memory(
            id="workspace-memory",
            content="workspace 私有上下文",
            category="work",
            scope="workspace",
            project="agent-bank",
        )
    )
    db.add(
        Memory(
            id="leader",
            content="潘总偏好数据驱动",
            category="people",
            subject="潘总",
            scope="global",
            importance=0.9,
        )
    )


def test_search_defaults_to_global_and_current_project_memories(tmp_path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    _seed_search_memories(db)

    results = db.search(query="ROI", project="agent-bank", top_k=10)
    ids = [memory.id for memory in results]

    assert "project-work" in ids
    assert "other-project" not in ids
    assert "workspace-memory" not in ids


def test_search_without_project_only_returns_global_scope(tmp_path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    _seed_search_memories(db)

    results = db.search(query="ROI", top_k=10)

    assert [memory.id for memory in results] == []


def test_search_explicit_workspace_scope_returns_workspace_memories(tmp_path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    _seed_search_memories(db)

    results = db.search(query="workspace", scope="workspace", project="agent-bank")

    assert [memory.id for memory in results] == ["workspace-memory"]


def test_search_matches_subject_and_tags(tmp_path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    _seed_search_memories(db)

    subject_results = db.search(query="潘总", category="people")
    tag_results = db.search(query="ppt", category="preference")

    assert [memory.id for memory in subject_results] == ["leader"]
    assert [memory.id for memory in tag_results] == ["global-pref"]


def test_search_orders_by_importance_then_updated_at(tmp_path):
    db = MarkdownMemoryStore(tmp_path / "memory")
    db.add(Memory(id="low", content="同一个关键词", importance=0.2))
    db.add(Memory(id="high", content="同一个关键词", importance=0.9))

    results = db.search(query="同一个关键词", top_k=10)

    assert [memory.id for memory in results] == ["high", "low"]
