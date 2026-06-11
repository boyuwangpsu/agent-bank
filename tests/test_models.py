"""Unit tests for Memory data model."""

import uuid
from datetime import datetime

import pytest

from agent_bank.models import Memory, ValidationError, VALID_SCOPES


class TestMemoryCreation:
    """Test Memory creation with defaults and explicit values."""

    def test_creation_with_defaults(self):
        """Memory created with only content should have sensible defaults."""
        memory = Memory(content="test content")

        # id should be a valid UUID v4
        uuid_obj = uuid.UUID(memory.id)
        assert uuid_obj.version == 4

        assert memory.content == "test content"
        assert memory.scope == "global"
        assert memory.tags == []
        assert memory.project is None

        # created_at should be a valid ISO timestamp
        parsed = datetime.fromisoformat(memory.created_at)
        assert parsed is not None

    def test_creation_with_all_fields(self):
        """Memory created with all fields should retain them."""
        memory = Memory(
            id="custom-id-123",
            content="项目使用 FastAPI",
            scope="project",
            tags=["architecture", "python"],
            project="my-project",
            created_at="2026-05-18T10:30:00",
        )

        assert memory.id == "custom-id-123"
        assert memory.content == "项目使用 FastAPI"
        assert memory.scope == "project"
        assert memory.tags == ["architecture", "python"]
        assert memory.project == "my-project"
        assert memory.created_at == "2026-05-18T10:30:00"

    def test_auto_generated_ids_are_unique(self):
        """Each Memory should get a unique auto-generated ID."""
        memories = [Memory(content="test") for _ in range(100)]
        ids = [m.id for m in memories]
        assert len(set(ids)) == 100


class TestMemoryValidation:
    """Test Memory validation rules."""

    def test_valid_memory_passes(self):
        """A well-formed memory should pass validation."""
        memory = Memory(content="valid content", scope="global")
        memory.validate()  # Should not raise

    def test_empty_content_rejected(self):
        """Empty string content should be rejected."""
        memory = Memory(content="")
        with pytest.raises(ValidationError, match="content 不能为空"):
            memory.validate()

    def test_whitespace_only_content_rejected(self):
        """Whitespace-only content should be rejected."""
        memory = Memory(content="   \t\n  ")
        with pytest.raises(ValidationError, match="content 不能为空"):
            memory.validate()

    def test_invalid_scope_rejected(self):
        """Invalid scope values should be rejected."""
        memory = Memory(content="test", scope="invalid")
        with pytest.raises(ValidationError, match="scope 必须是"):
            memory.validate()

    def test_all_valid_scopes_accepted(self):
        """All valid scope values should pass validation."""
        for scope in VALID_SCOPES:
            memory = Memory(content="test", scope=scope)
            memory.validate()  # Should not raise

    def test_empty_tag_rejected(self):
        """Empty string in tags should be rejected."""
        memory = Memory(content="test", tags=["valid", ""])
        with pytest.raises(ValidationError, match="tags 中不能包含空字符串"):
            memory.validate()

    def test_whitespace_only_tag_rejected(self):
        """Whitespace-only tag should be rejected."""
        memory = Memory(content="test", tags=["valid", "   "])
        with pytest.raises(ValidationError, match="tags 中不能包含空字符串"):
            memory.validate()


class TestMemorySerialization:
    """Test to_dict and from_dict round-trip."""

    def test_to_dict_contains_all_fields(self):
        """to_dict should include all Memory fields."""
        memory = Memory(
            id="test-id",
            content="hello world",
            scope="project",
            tags=["tag1", "tag2"],
            project="proj-a",
            created_at="2026-01-01T00:00:00",
        )
        d = memory.to_dict()

        assert d == {
            "id": "test-id",
            "content": "hello world",
            "category": "preference",
            "scope": "project",
            "subject": None,
            "source": "user_stated",
            "importance": 0.5,
            "tags": ["tag1", "tag2"],
            "project": "proj-a",
            "timeline": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": memory.updated_at,
            "last_accessed": None,
            "access_count": 0,
        }

    def test_from_dict_restores_memory(self):
        """from_dict should restore a Memory from a dictionary."""
        data = {
            "id": "abc-123",
            "content": "some content",
            "scope": "workspace",
            "tags": ["dev"],
            "project": "my-proj",
            "created_at": "2026-05-18T12:00:00",
        }
        memory = Memory.from_dict(data)

        assert memory.id == "abc-123"
        assert memory.content == "some content"
        assert memory.scope == "workspace"
        assert memory.tags == ["dev"]
        assert memory.project == "my-proj"
        assert memory.created_at == "2026-05-18T12:00:00"

    def test_round_trip(self):
        """Serializing then deserializing should produce an equivalent Memory."""
        original = Memory(
            content="用户偏好 ruff",
            scope="global",
            tags=["preference", "python"],
            project=None,
        )
        restored = Memory.from_dict(original.to_dict())

        assert restored.id == original.id
        assert restored.content == original.content
        assert restored.scope == original.scope
        assert restored.tags == original.tags
        assert restored.project == original.project
        assert restored.created_at == original.created_at

    def test_round_trip_with_project(self):
        """Round-trip should work for project-scoped memories."""
        original = Memory(
            content="FastAPI project",
            scope="project",
            tags=["arch"],
            project="backend-api",
        )
        restored = Memory.from_dict(original.to_dict())

        assert restored.id == original.id
        assert restored.content == original.content
        assert restored.scope == original.scope
        assert restored.tags == original.tags
        assert restored.project == original.project
        assert restored.created_at == original.created_at

    def test_from_dict_with_missing_fields_uses_defaults(self):
        """from_dict should handle missing fields gracefully."""
        data = {"content": "minimal"}
        memory = Memory.from_dict(data)

        assert memory.content == "minimal"
        assert memory.scope == "global"
        assert memory.tags == []
        assert memory.project is None
        # id and created_at should be auto-generated
        uuid.UUID(memory.id)  # Should not raise
