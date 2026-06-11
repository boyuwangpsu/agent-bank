"""Tests for Markdown-backed memory storage."""

from pathlib import Path

from agent_bank.markdown_store import MarkdownMemoryStore
from agent_bank.models import Memory


def test_add_writes_category_file_and_memory_map(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    memory = store.add(
        Memory(
            id="leader-roi",
            content="潘总偏好 ROI 分析",
            category="people",
            subject="潘总",
            importance=0.9,
            tags=["leader", "roi"],
        )
    )

    person_file = tmp_path / "memory" / "people" / "pan-zong.md"
    map_file = tmp_path / "memory" / "MEMORY_MAP.md"

    assert memory.id == "leader-roi"
    assert person_file.exists()
    assert 'id = "people-pan-zong"' in person_file.read_text(encoding="utf-8")
    assert "潘总偏好 ROI 分析" in person_file.read_text(encoding="utf-8")
    assert map_file.exists()
    assert "people/pan-zong.md" in map_file.read_text(encoding="utf-8")


def test_reads_user_authored_markdown_with_frontmatter(tmp_path: Path):
    root = tmp_path / "memory"
    people_dir = root / "people"
    people_dir.mkdir(parents=True)
    (people_dir / "pan.md").write_text(
        """+++
id = "people-pan"
category = "people"
subject = "潘总"
scope = "global"
status = "active"
importance = 0.9
tags = ["leader"]
created_at = "2026-06-10T10:00:00"
updated_at = "2026-06-10T10:00:00"
+++

# 潘总

## 当前认知

- 潘总偏好简洁。
  <!-- agent-bank:id=mem-pan-simple status=active source=user_stated importance=0.9 updated_at=2026-06-10T10:00:00 -->
""",
        encoding="utf-8",
    )

    store = MarkdownMemoryStore(root)
    results = store.search(query="简洁", category="people")

    assert [memory.id for memory in results] == ["mem-pan-simple"]
    assert results[0].subject == "潘总"
    assert results[0].tags == ["leader"]


def test_govern_rejected_fact_is_excluded_from_active_results(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    memory = store.add(Memory(content="临时错误认知", category="work", subject="旧项目"))

    fact = store.govern_fact(
        memory_id=memory.id,
        action="reject",
        reason="用户标记错误",
    )

    assert fact is not None
    assert fact["status"] == "rejected"
    assert store.search(query="临时错误认知") == []
    file_text = (tmp_path / "memory" / "work" / "jiu-xiang-mu.md").read_text(
        encoding="utf-8"
    )
    assert "status=rejected" in file_text
    assert "用户标记错误" in file_text


def test_merge_memories_marks_sources_merged_and_creates_canonical_fact(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    first = store.add(
        Memory(
            id="simple",
            content="潘总偏好简洁",
            category="people",
            subject="潘总",
            tags=["leader"],
            importance=0.7,
        )
    )
    second = store.add(
        Memory(
            id="roi",
            content="潘总要求 ROI 分析",
            category="people",
            subject="潘总",
            tags=["roi"],
            importance=0.9,
        )
    )

    merged = store.merge_memories(
        memory_ids=[first.id, second.id],
        content="潘总偏好简洁，并要求 ROI 分析",
        subject="潘总",
        reason="合并重复事实",
    )

    assert merged is not None
    assert store.search(query="潘总") == [merged]
    snapshot = store.graph_snapshot()
    source_statuses = {
        fact["memory_id"]: fact["status"]
        for fact in snapshot["facts"]
        if fact["memory_id"] in {first.id, second.id}
    }
    assert source_statuses == {"simple": "merged", "roi": "merged"}
    assert snapshot["timeline"][0]["event_type"] == "fact_merged"


def test_search_respects_scope_project_subject_tags_and_order(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.add(
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
    store.add(
        Memory(
            id="other-project",
            content="其他项目的 ROI 记忆",
            category="work",
            scope="project",
            project="other",
            importance=1.0,
        )
    )
    store.add(Memory(id="leader", content="潘总偏好数据驱动", category="people", subject="潘总"))
    store.add(Memory(id="ppt", content="PPT 默认不超过 15 页", category="preference", tags=["ppt"]))

    assert [m.id for m in store.search(query="ROI", project="agent-bank")] == [
        "project-work"
    ]
    assert [m.id for m in store.search(query="潘总", category="people")] == ["leader"]
    assert [m.id for m in store.search(query="ppt", category="preference")] == ["ppt"]
