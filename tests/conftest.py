"""Shared fixtures for agent-bank tests."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_storage_path(tmp_path: Path) -> Path:
    """Provide a temporary storage path for MemoryStore tests.

    Returns a path to a temporary memories.json file that is
    automatically cleaned up after each test.
    """
    return tmp_path / "memories.json"


@pytest.fixture
def tmp_storage_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for storage-related tests.

    The directory exists but contains no files, useful for testing
    auto-creation of memories.json.
    """
    storage_dir = tmp_path / ".agent-bank"
    storage_dir.mkdir()
    return storage_dir
