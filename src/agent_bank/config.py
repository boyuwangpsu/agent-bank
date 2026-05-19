"""Configuration for agent-bank."""

import os
from pathlib import Path


def get_db_path() -> Path:
    """Get the SQLite database path.

    Priority:
    1. AGENT_BANK_DB environment variable
    2. ~/.agent-bank/memory.db (default)
    """
    env_path = os.environ.get("AGENT_BANK_DB")
    if env_path:
        # Expand ~ in env var
        return Path(env_path).expanduser()
    return Path.home() / ".agent-bank" / "memory.db"


def detect_project() -> str | None:
    """Detect current project identifier.

    Priority:
    1. AGENT_BANK_PROJECT environment variable (if not "auto")
    2. Git remote origin name
    3. Current working directory basename
    """
    env_project = os.environ.get("AGENT_BANK_PROJECT")
    if env_project and env_project != "auto":
        return env_project

    # Try git remote
    try:
        import subprocess
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Extract repo name from URL
            name = url.rstrip("/").split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
            return name
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback to cwd name
    try:
        return Path.cwd().name
    except OSError:
        return None
