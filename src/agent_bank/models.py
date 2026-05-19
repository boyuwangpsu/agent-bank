"""Memory data model with structured categories for workplace AI memory."""

from dataclasses import dataclass, field
from datetime import datetime
import uuid


# Memory categories (what kind of memory)
VALID_CATEGORIES = ("identity", "people", "work", "knowledge", "preference")

# Memory scopes (visibility)
VALID_SCOPES = ("global", "project", "workspace")

# Source of information
VALID_SOURCES = ("user_stated", "observed", "inferred")


class ValidationError(Exception):
    """Raised when Memory validation fails."""
    pass


@dataclass
class Memory:
    """A single memory entry in agent-bank.

    Attributes:
        id: Unique identifier (UUID v4).
        content: The memory content text (compiled truth — current understanding).
        category: Type of memory (identity/people/work/knowledge/preference).
        scope: Visibility scope (global/project/workspace).
        subject: Who/what this memory is about (e.g., leader name, project name).
        source: How this information was obtained.
        importance: 0.0-1.0, higher = more important.
        tags: Keyword tags.
        project: Project identifier (for project/workspace scoped memories).
        timeline: Append-only history of changes to this memory.
        created_at: ISO timestamp of creation.
        updated_at: ISO timestamp of last update.
        last_accessed: ISO timestamp of last recall hit.
        access_count: Number of times this memory was returned in recall.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    category: str = "preference"
    scope: str = "global"
    subject: str | None = None
    source: str = "user_stated"
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)
    project: str | None = None
    timeline: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str | None = None
    access_count: int = 0

    def validate(self) -> None:
        """Validate memory fields."""
        if not self.content or not self.content.strip():
            raise ValidationError("content 不能为空")
        if self.category not in VALID_CATEGORIES:
            raise ValidationError(f"category 必须是 {VALID_CATEGORIES} 之一")
        if self.scope not in VALID_SCOPES:
            raise ValidationError(f"scope 必须是 {VALID_SCOPES} 之一")
        if self.source not in VALID_SOURCES:
            raise ValidationError(f"source 必须是 {VALID_SOURCES} 之一")
        if not (0.0 <= self.importance <= 1.0):
            raise ValidationError("importance 必须在 0.0-1.0 之间")

    def touch(self) -> None:
        """Update access tracking (called on recall hit)."""
        self.last_accessed = datetime.now().isoformat()
        self.access_count += 1

    def update_content(self, new_content: str, reason: str = "") -> None:
        """Update compiled truth, preserving history in timeline."""
        self.timeline.append({
            "date": datetime.now().isoformat(),
            "old_content": self.content,
            "reason": reason,
        })
        self.content = new_content
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "scope": self.scope,
            "subject": self.subject,
            "source": self.source,
            "importance": self.importance,
            "tags": list(self.tags),
            "project": self.project,
            "timeline": list(self.timeline),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        """Deserialize from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            content=data.get("content", ""),
            category=data.get("category", "preference"),
            scope=data.get("scope", "global"),
            subject=data.get("subject"),
            source=data.get("source", "user_stated"),
            importance=data.get("importance", 0.5),
            tags=data.get("tags", []),
            project=data.get("project"),
            timeline=data.get("timeline", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            last_accessed=data.get("last_accessed"),
            access_count=data.get("access_count", 0),
        )
