"""Markdown-backed memory store.

Markdown files are the source of truth. Generated indexes such as
``MEMORY_MAP.md`` are read models that help agents decide which files to read.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import tempfile
import tomllib

from agent_bank.models import Memory

ACTIVE_STATUSES = ("active", "confirmed")
INACTIVE_STATUSES = ("merged", "rejected", "stale")
GOVERN_ACTIONS = {
    "confirm": ("confirmed", "fact_confirmed"),
    "reject": ("rejected", "fact_rejected"),
    "stale": ("stale", "fact_stale"),
}

FACT_COMMENT_RE = re.compile(r"<!--\s*agent-bank:(.*?)\s*-->")
FACT_META_RE = re.compile(r"(\w+)=((?:\"[^\"]*\")|(?:[^\s]+))")
TIMELINE_RE = re.compile(r"^-\s+([^|]+)\|\s*([^|]+)\|\s*(.*)$")


@dataclass
class MarkdownFact:
    memory: Memory
    status: str = "active"
    fact_id: str | None = None
    reason: str = ""

    def to_snapshot(self) -> dict:
        return {
            "id": self.fact_id or f"fact:{self.memory.id}",
            "memory_id": self.memory.id,
            "node_id": _node_id_for_memory(self.memory),
            "statement": self.memory.content,
            "category": self.memory.category,
            "status": self.status,
            "confidence": self.memory.importance,
            "valid_from": self.memory.created_at,
            "valid_to": None if self.status in ACTIVE_STATUSES else self.memory.updated_at,
            "evidence_event_id": f"event:{self.memory.id}:remembered",
            "created_at": self.memory.created_at,
            "updated_at": self.memory.updated_at,
            "metadata": {"source": self.memory.source, "reason": self.reason},
            "subject": self.memory.subject,
            "source": self.memory.source,
        }


@dataclass
class MarkdownDocument:
    path: Path
    meta: dict
    facts: list[MarkdownFact] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)


class MarkdownMemoryStore:
    """Memory storage backed by categorized Markdown files."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def add(self, memory: Memory) -> Memory:
        """Insert a new memory fact into its subject Markdown file."""
        memory.validate()
        path = self._path_for_memory(memory)
        document = self._read_document(path, default_memory=memory)
        document.facts.append(MarkdownFact(memory=memory, status="active"))
        document.timeline.insert(0, _event(memory, "remembered", memory.content))
        for entry in reversed(memory.timeline):
            reason = entry.get("reason") or "记忆被更新"
            old_content = entry.get("old_content", "")
            document.timeline.insert(
                0,
                _event(
                    memory,
                    "updated",
                    f"{reason}：旧认知：{old_content} → 新认知：{memory.content}",
                    occurred_at=entry.get("date"),
                ),
            )
        self._write_document(document)
        self.rebuild_map()
        return memory

    def get(self, memory_id: str) -> Memory | None:
        """Get a memory by ID, including inactive facts."""
        for fact in self._all_facts(include_inactive=True):
            if fact.memory.id == memory_id:
                return fact.memory
        return None

    def update(self, memory: Memory) -> None:
        """Update an existing memory fact."""
        for document in self._read_documents():
            changed = False
            for fact in document.facts:
                if fact.memory.id == memory.id:
                    fact.memory = memory
                    changed = True
            if changed:
                document.timeline.insert(
                    0, _event(memory, "updated", memory.timeline[-1]["reason"] if memory.timeline else memory.content)
                )
                self._write_document(document)
                self.rebuild_map()
                return

    def delete(self, memory_id: str) -> bool:
        """Delete a memory fact."""
        for document in self._read_documents():
            before = len(document.facts)
            document.facts = [fact for fact in document.facts if fact.memory.id != memory_id]
            if len(document.facts) != before:
                document.timeline.insert(
                    0,
                    {
                        "event_type": "forgotten",
                        "content": f"删除记忆 {memory_id}",
                        "memory_id": memory_id,
                        "occurred_at": _now(),
                    },
                )
                self._write_document(document)
                self.rebuild_map()
                return True
        return False

    def search(
        self,
        query: str | None = None,
        category: str | None = None,
        scope: str | None = None,
        subject: str | None = None,
        project: str | None = None,
        top_k: int = 10,
    ) -> list[Memory]:
        """Search active Markdown facts with lightweight keyword matching."""
        memories = self.get_all(category=category)
        filtered = [
            memory
            for memory in memories
            if _scope_matches(memory, scope=scope, project=project)
            and (not subject or memory.subject == subject)
            and _query_matches(memory, query)
        ]
        filtered.sort(key=lambda m: (m.importance, m.updated_at), reverse=True)
        return filtered[:top_k]

    def get_all(self, category: str | None = None) -> list[Memory]:
        """Get active memories, optionally filtered by category."""
        facts = self._all_facts(include_inactive=False)
        memories = [
            fact.memory
            for fact in facts
            if category is None or fact.memory.category == category
        ]
        memories.sort(key=lambda m: (m.category, -m.importance, m.updated_at))
        return memories

    def count(self) -> dict[str, int]:
        """Get active memory counts by category."""
        counts: dict[str, int] = defaultdict(int)
        for memory in self.get_all():
            counts[memory.category] += 1
        result = dict(counts)
        result["total"] = sum(result.values())
        return result

    def govern_fact(
        self,
        *,
        fact_id: str | None = None,
        memory_id: str | None = None,
        action: str,
        reason: str = "",
    ) -> dict | None:
        """Apply a governance action to a Markdown fact."""
        if action not in GOVERN_ACTIONS or (not fact_id and not memory_id):
            return None
        new_status, event_type = GOVERN_ACTIONS[action]

        for document in self._read_documents():
            for fact in document.facts:
                if fact.fact_id == fact_id or fact.memory.id == memory_id:
                    fact.status = new_status
                    fact.reason = reason.strip()
                    fact.memory.updated_at = _now()
                    document.timeline.insert(
                        0,
                        _event(
                            fact.memory,
                            event_type,
                            reason.strip() or fact.memory.content,
                        ),
                    )
                    self._write_document(document)
                    self.rebuild_map()
                    return fact.to_snapshot()
        return None

    def merge_memories(
        self,
        *,
        memory_ids: list[str],
        content: str,
        category: str | None = None,
        subject: str | None = None,
        reason: str = "",
    ) -> Memory | None:
        """Merge source facts into one canonical active fact."""
        if len(memory_ids) < 2 or not content.strip():
            return None
        sources = [self.get(memory_id) for memory_id in memory_ids]
        if any(memory is None for memory in sources):
            return None

        source_memories = [memory for memory in sources if memory is not None]
        merged = Memory(
            content=content.strip(),
            category=category or source_memories[0].category,
            scope=source_memories[0].scope,
            subject=subject or source_memories[0].subject,
            source="user_stated",
            importance=max(memory.importance for memory in source_memories),
            tags=sorted({tag for memory in source_memories for tag in memory.tags}),
            project=source_memories[0].project,
            timeline=[
                {
                    "date": _now(),
                    "old_content": " | ".join(memory.content for memory in source_memories),
                    "reason": reason,
                }
            ],
        )
        self.add(merged)

        for document in self._read_documents():
            changed = False
            for fact in document.facts:
                if fact.memory.id in memory_ids:
                    fact.status = "merged"
                    fact.reason = reason.strip()
                    fact.memory.updated_at = _now()
                    changed = True
            if changed:
                document.timeline.insert(
                    0,
                    _event(
                        merged,
                        "fact_merged",
                        reason.strip() or f"合并为：{merged.content}",
                    ),
                )
                self._write_document(document)
        self.rebuild_map()
        return self.get(merged.id)

    def merge_candidates(self, top_k: int = 20) -> list[dict]:
        """Suggest active memory groups that may benefit from merging."""
        groups: dict[tuple[str, str], list[Memory]] = defaultdict(list)
        for memory in self.get_all():
            groups[(memory.category, memory.subject or "")].append(memory)

        candidates = []
        for (category, subject), memories in groups.items():
            if len(memories) < 2 or not subject:
                continue
            memories.sort(key=lambda m: m.created_at)
            candidates.append(
                {
                    "category": category,
                    "subject": subject,
                    "count": len(memories),
                    "memory_ids": [memory.id for memory in memories],
                    "contents": [memory.content for memory in memories],
                }
            )
        candidates.sort(key=lambda item: item["count"], reverse=True)
        return candidates[:top_k]

    def graph_snapshot(self) -> dict:
        """Return graph-like data derived from Markdown facts."""
        nodes = {
            "user:me": {
                "id": "user:me",
                "name": "我",
                "node_type": "user",
                "category": "identity",
            }
        }
        edges = []
        facts = []
        timeline = []
        for fact in self._all_facts(include_inactive=True):
            memory = fact.memory
            node_id = _node_id_for_memory(memory)
            nodes[node_id] = {
                "id": node_id,
                "name": _node_name_for_memory(memory),
                "node_type": _node_type_for_category(memory.category),
                "category": memory.category,
                "scope": memory.scope,
                "project": memory.project,
                "metadata": {"tags": memory.tags},
                "created_at": memory.created_at,
                "updated_at": memory.updated_at,
            }
            relation = _relation_for_category(memory.category)
            if relation:
                edges.append(
                    {
                        "id": f"edge:user:me:{node_id}:{relation}:{memory.id}",
                        "source_node_id": "user:me",
                        "target_node_id": node_id,
                        "relation": relation,
                        "memory_id": memory.id,
                        "created_at": memory.created_at,
                        "updated_at": memory.updated_at,
                        "metadata": {},
                    }
                )
            facts.append(fact.to_snapshot())
            timeline.append(
                _event(
                    memory,
                    "remembered",
                    memory.content,
                    occurred_at=memory.created_at,
                )
            )

        for document in self._read_documents():
            timeline.extend(document.timeline)

        timeline.sort(key=lambda item: item.get("occurred_at", ""), reverse=True)
        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "facts": facts,
            "timeline": timeline,
        }

    def rebuild_map(self) -> Path:
        """Regenerate MEMORY_MAP.md from active Markdown facts."""
        path = self.root / "MEMORY_MAP.md"
        lines = [
            "# Memory Map",
            "",
            "## 使用规则",
            "",
            "1. 任务开始前先读本文件。",
            "2. 根据人物、项目、关键词读取对应记忆文件。",
            "3. 发现稳定偏好、人物风格、长期事实时，调用 remember 更新记忆。",
            "",
        ]
        by_category: dict[str, list[Memory]] = defaultdict(list)
        for memory in self.get_all():
            by_category[memory.category].append(memory)

        sections = [
            ("identity", "Profile"),
            ("people", "People"),
            ("work", "Work"),
            ("knowledge", "Knowledge"),
            ("preference", "Preferences"),
        ]
        for category, title in sections:
            memories = by_category.get(category, [])
            if not memories:
                continue
            lines.extend([f"## {title}", "", "| 主体 | 文件 | 摘要 | 标签 | 更新时间 |", "|---|---|---|---|---|"])
            for memory in sorted(memories, key=lambda m: (m.subject or "", m.updated_at)):
                relative = self._path_for_memory(memory).relative_to(self.root).as_posix()
                subject = memory.subject or _category_label(memory.category)
                summary = memory.content.replace("|", "｜")[:80]
                tags = ", ".join(memory.tags)
                lines.append(
                    f"| {subject} | {relative} | {summary} | {tags} | {memory.updated_at[:10]} |"
                )
            lines.append("")

        _atomic_write(path, "\n".join(lines).rstrip() + "\n")
        return path

    def _path_for_memory(self, memory: Memory) -> Path:
        directory = self.root / _directory_for_category(memory.category)
        name_source = memory.subject or _category_label(memory.category)
        return directory / f"{_slug(name_source)}.md"

    def _all_facts(self, *, include_inactive: bool) -> list[MarkdownFact]:
        facts = []
        for document in self._read_documents():
            facts.extend(
                fact
                for fact in document.facts
                if include_inactive or fact.status in ACTIVE_STATUSES
            )
        return facts

    def _read_documents(self) -> list[MarkdownDocument]:
        documents = []
        if not self.root.exists():
            return documents
        for path in sorted(self.root.rglob("*.md")):
            if path.name == "MEMORY_MAP.md":
                continue
            documents.append(self._read_document(path))
        return documents

    def _read_document(
        self, path: Path, *, default_memory: Memory | None = None
    ) -> MarkdownDocument:
        if not path.exists():
            meta = _meta_from_memory(default_memory) if default_memory else {}
            return MarkdownDocument(path=path, meta=meta)

        text = path.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(text)
        document = MarkdownDocument(path=path, meta=meta)
        document.facts = _parse_facts(body, meta)
        document.timeline = _parse_timeline(body)
        return document

    def _write_document(self, document: MarkdownDocument) -> None:
        if document.facts:
            primary = document.facts[0].memory
            document.meta = _meta_from_memory(primary) | {
                key: value for key, value in document.meta.items() if key == "id"
            }
            document.meta.setdefault("id", _document_id(primary))
            document.meta["tags"] = sorted(
                {tag for fact in document.facts for tag in fact.memory.tags}
            )
            document.meta["importance"] = max(
                fact.memory.importance for fact in document.facts
            )
            document.meta["updated_at"] = max(
                fact.memory.updated_at for fact in document.facts
            )
        body = _render_document(document)
        _atomic_write(document.path, body)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("+++\n"):
        return {}, text
    end = text.find("\n+++", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :].lstrip("\n")
    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError:
        return {}, body
    return data, body


def _parse_facts(body: str, meta: dict) -> list[MarkdownFact]:
    lines = body.splitlines()
    facts = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:].strip()
        if not content or content.startswith("20"):
            continue
        comment_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        match = FACT_COMMENT_RE.search(comment_line)
        if not match:
            continue
        fact_meta = _parse_fact_meta(match.group(1))
        memory = Memory(
            id=fact_meta.get("id", ""),
            content=content,
            category=fact_meta.get("category", meta.get("category", "preference")),
            scope=fact_meta.get("scope", meta.get("scope", "global")),
            subject=fact_meta.get("subject", meta.get("subject")) or None,
            source=fact_meta.get("source", "user_stated"),
            importance=float(fact_meta.get("importance", meta.get("importance", 0.5))),
            tags=list(meta.get("tags", [])),
            project=fact_meta.get("project", meta.get("project")) or None,
            created_at=str(meta.get("created_at", fact_meta.get("updated_at", _now()))),
            updated_at=fact_meta.get("updated_at", str(meta.get("updated_at", _now()))),
            last_accessed=fact_meta.get("last_accessed") or None,
            access_count=int(fact_meta.get("access_count", "0")),
        )
        facts.append(
            MarkdownFact(
                memory=memory,
                status=fact_meta.get("status", meta.get("status", "active")),
                fact_id=f"fact:{memory.id}",
                reason=fact_meta.get("reason", ""),
            )
        )
    return facts


def _parse_fact_meta(raw: str) -> dict[str, str]:
    result = {}
    for key, value in FACT_META_RE.findall(raw):
        result[key] = value.strip('"')
    return result


def _escape_meta(value: str) -> str:
    return value.replace('"', "'")


def _parse_timeline(body: str) -> list[dict]:
    timeline = []
    in_timeline = False
    for line in body.splitlines():
        if line.startswith("## 演进记录"):
            in_timeline = True
            continue
        if in_timeline and line.startswith("## "):
            break
        if not in_timeline:
            continue
        match = TIMELINE_RE.match(line.strip())
        if match:
            occurred_at, event_type, content = match.groups()
            timeline.append(
                {
                    "id": f"event:{occurred_at}:{event_type}:{len(timeline)}",
                    "memory_id": "",
                    "event_type": event_type.strip(),
                    "content": content.strip(),
                    "category": "",
                    "subject": None,
                    "source": "user_stated",
                    "occurred_at": occurred_at.strip(),
                    "metadata": {},
                }
            )
    return timeline


def _render_document(document: MarkdownDocument) -> str:
    lines = ["+++"]
    for key, value in document.meta.items():
        lines.append(_toml_line(key, value))
    lines.extend(["+++", "", f"# {document.meta.get('subject') or document.meta.get('category', '记忆')}", "", "## 当前认知", ""])
    for fact in document.facts:
        memory = fact.memory
        lines.append(f"- {memory.content}")
        lines.append(
            "  <!-- agent-bank:"
            f"id={memory.id} status={fact.status} category={memory.category} "
            f"scope={memory.scope} subject=\"{_escape_meta(memory.subject or '')}\" "
            f"project=\"{_escape_meta(memory.project or '')}\" source={memory.source} "
            f"importance={memory.importance} updated_at={memory.updated_at} "
            f"last_accessed={memory.last_accessed or ''} access_count={memory.access_count} "
            f"reason=\"{_escape_meta(fact.reason)}\""
            " -->"
        )
    lines.extend(["", "## 演进记录", ""])
    seen = set()
    for event in document.timeline:
        key = (event.get("occurred_at"), event.get("event_type"), event.get("content"))
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f"- {event.get('occurred_at', _now())} | {event.get('event_type', 'updated')} | {event.get('content', '')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _toml_line(key: str, value) -> str:
    if isinstance(value, list):
        items = ", ".join(f'"{item}"' for item in value)
        return f"{key} = [{items}]"
    if isinstance(value, (int, float)):
        return f"{key} = {value}"
    return f'{key} = "{str(value)}"'


def _meta_from_memory(memory: Memory | None) -> dict:
    if memory is None:
        return {}
    return {
        "id": _document_id(memory),
        "category": memory.category,
        "subject": memory.subject or "",
        "scope": memory.scope,
        "status": "active",
        "importance": memory.importance,
        "tags": memory.tags,
        "project": memory.project or "",
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def _event(
    memory: Memory, event_type: str, content: str, *, occurred_at: str | None = None
) -> dict:
    event_time = occurred_at or _now()
    return {
        "id": f"event:{memory.id}:{event_type}:{event_time}",
        "memory_id": memory.id,
        "event_type": event_type,
        "content": content,
        "category": memory.category,
        "subject": memory.subject,
        "source": memory.source,
        "occurred_at": event_time,
        "metadata": {},
    }


def _scope_matches(
    memory: Memory, *, scope: str | None = None, project: str | None = None
) -> bool:
    if scope and scope != "all":
        if memory.scope != scope:
            return False
        if scope in ("project", "workspace") and project:
            return memory.project == project
        return True
    if project:
        return memory.scope == "global" or (
            memory.scope == "project" and memory.project == project
        )
    return memory.scope == "global"


def _query_matches(memory: Memory, query: str | None) -> bool:
    if not query:
        return True
    haystack = " ".join(
        [
            memory.content,
            memory.subject or "",
            " ".join(memory.tags),
        ]
    ).lower()
    keywords = [part.strip().lower() for part in query.split() if part.strip()]
    return any(keyword in haystack for keyword in keywords)


def _directory_for_category(category: str) -> str:
    return {
        "identity": "profile",
        "people": "people",
        "work": "work",
        "knowledge": "knowledge",
        "preference": "profile",
    }.get(category, "misc")


def _category_label(category: str) -> str:
    return {
        "identity": "me",
        "preference": "preferences",
        "knowledge": "glossary",
        "work": "current",
        "people": "people",
    }.get(category, category)


def _document_id(memory: Memory) -> str:
    return f"{memory.category}-{_slug(memory.subject or _category_label(memory.category))}"


def _node_id_for_memory(memory: Memory) -> str:
    return f"{_node_type_for_category(memory.category)}:{_slug(_node_name_for_memory(memory))}"


def _node_name_for_memory(memory: Memory) -> str:
    if memory.category == "identity":
        return "我"
    return memory.subject or memory.content[:40]


def _node_type_for_category(category: str) -> str:
    return {
        "identity": "user",
        "people": "person",
        "work": "project",
        "knowledge": "concept",
        "preference": "preference",
    }.get(category, category)


def _relation_for_category(category: str) -> str | None:
    return {
        "people": "knows_person",
        "work": "works_on",
        "knowledge": "knows_concept",
        "preference": "prefers",
    }.get(category)


PINYIN = {
    "潘": "pan",
    "总": "zong",
    "旧": "jiu",
    "项": "xiang",
    "目": "mu",
    "李": "li",
    "我": "wo",
}


def _slug(value: str) -> str:
    parts = []
    for char in value.strip().lower():
        if char.isascii() and char.isalnum():
            parts.append(char)
        elif char in PINYIN:
            parts.extend(["-", PINYIN[char], "-"])
        else:
            parts.append("-")
    slug = re.sub(r"-+", "-", "".join(parts)).strip("-")
    return slug or "memory"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _now() -> str:
    return datetime.now().isoformat()
