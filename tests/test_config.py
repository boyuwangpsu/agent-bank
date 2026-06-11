"""Tests for agent_bank.config module."""

from pathlib import Path
from unittest.mock import patch

from agent_bank.config import (
    detect_project,
    get_dashboard_path,
    get_memory_root,
)


def test_get_dashboard_path_defaults_to_home_dashboard(monkeypatch):
    monkeypatch.delenv("AGENT_BANK_DASHBOARD", raising=False)

    assert get_dashboard_path() == Path.home() / ".agent-bank" / "dashboard.html"


def test_get_dashboard_path_uses_env_and_expands_user(monkeypatch):
    monkeypatch.setenv("AGENT_BANK_DASHBOARD", "~/.agent-bank/view.html")

    assert get_dashboard_path() == Path.home() / ".agent-bank" / "view.html"


def test_get_memory_root_defaults_to_home_memory_dir(monkeypatch):
    monkeypatch.delenv("AGENT_BANK_MEMORY_DIR", raising=False)

    assert get_memory_root() == Path.home() / ".agent-bank" / "memory"


def test_get_memory_root_uses_env_and_expands_user(monkeypatch):
    monkeypatch.setenv("AGENT_BANK_MEMORY_DIR", "~/.agent-bank/work-memory")

    assert get_memory_root() == Path.home() / ".agent-bank" / "work-memory"


def test_detect_project_returns_env_variable_when_set(monkeypatch):
    monkeypatch.setenv("AGENT_BANK_PROJECT", "my-project")

    assert detect_project() == "my-project"


def test_detect_project_auto_uses_git_remote(monkeypatch):
    monkeypatch.setenv("AGENT_BANK_PROJECT", "auto")
    fake_result = type("Result", (), {"returncode": 0, "stdout": "git@github.com:x/agent-bank.git\n"})

    with patch("subprocess.run", return_value=fake_result):
        assert detect_project() == "agent-bank"


def test_detect_project_falls_back_to_cwd_basename(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENT_BANK_PROJECT", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_result = type("Result", (), {"returncode": 1, "stdout": ""})

    with patch("subprocess.run", return_value=fake_result):
        assert detect_project() == tmp_path.name


def test_detect_project_returns_none_when_cwd_fails(monkeypatch):
    monkeypatch.delenv("AGENT_BANK_PROJECT", raising=False)
    fake_result = type("Result", (), {"returncode": 1, "stdout": ""})

    with (
        patch("subprocess.run", return_value=fake_result),
        patch("agent_bank.config.Path.cwd", side_effect=OSError("no cwd")),
    ):
        assert detect_project() is None
