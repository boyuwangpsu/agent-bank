"""Configuration for agent-bank."""

import os
from pathlib import Path


def get_dashboard_path() -> Path:
    """Get the generated dashboard path.

    Priority:
    1. AGENT_BANK_DASHBOARD environment variable
    2. ~/.agent-bank/dashboard.html (default)
    """
    env_path = os.environ.get("AGENT_BANK_DASHBOARD")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".agent-bank" / "dashboard.html"


def get_memory_root() -> Path:
    """Get the Markdown memory root directory.

    Priority:
    1. AGENT_BANK_MEMORY_DIR environment variable
    2. ~/.agent-bank/memory (default)
    """
    env_path = os.environ.get("AGENT_BANK_MEMORY_DIR")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".agent-bank" / "memory"


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
