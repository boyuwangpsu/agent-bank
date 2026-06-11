# Markdown-Only Memory Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SQLite runtime storage with Markdown files as the single source of truth, with generated `MEMORY_MAP.md` as the navigation layer.

**Architecture:** Add a Markdown-native store that preserves the existing server-facing API (`add`, `search`, `get_all`, `govern_fact`, `merge_memories`, `graph_snapshot`) while persisting every fact in categorized Markdown files. The server reads and writes through this store, steering points agents to `MEMORY_MAP.md`, and visualization reads parsed Markdown state.

**Tech Stack:** Python 3.11+, standard-library `tomllib`, Markdown files with TOML frontmatter, pytest.

---

### Task 1: Markdown Store Core

**Files:**
- Create: `src/agent_bank/markdown_store.py`
- Modify: `src/agent_bank/config.py`
- Test: `tests/test_markdown_store.py`

- [ ] Write failing tests for creating category files, parsing user-authored Markdown, searching active facts, and generating `MEMORY_MAP.md`.
- [ ] Implement `MarkdownMemoryStore` with atomic writes and TOML frontmatter parsing.
- [ ] Verify targeted store tests pass.

### Task 2: Server Runtime Switch

**Files:**
- Modify: `src/agent_bank/server.py`
- Modify: `src/agent_bank/steering.py`
- Modify: `src/agent_bank/visualize.py`
- Test: `tests/test_server.py`, `tests/test_visualize.py`

- [ ] Write failing server tests showing `remember` writes Markdown and `export_md` rebuilds the map.
- [ ] Replace `_get_db()` with `_get_store()` and remove SQLite path usage from runtime.
- [ ] Update steering copy so the default behavior is “read `MEMORY_MAP.md`, then relevant Markdown files.”
- [ ] Verify server and visualization tests pass.

### Task 3: Retire SQLite Surface

**Files:**
- Remove or replace: `src/agent_bank/db.py`
- Modify: `tests/test_store.py`, `tests/test_search.py`, `tests/test_markdown_export.py`
- Modify: `README.md`

- [ ] Replace DB tests with Markdown store tests or remove duplicate SQLite-only tests.
- [ ] Keep backward-compatible import only if needed for old tests, but no SQLite operations.
- [ ] Update docs to describe Markdown as the source of truth.
- [ ] Run full test suite.

### Self-Review

- Scope is focused on storage replacement only; no vector search, no UI redesign, no new product tools.
- Existing MCP tool names remain stable.
- `MEMORY_MAP.md` is generated and should not be the fact source.
- Markdown frontmatter and fact comments provide enough structure for governance without introducing another database.
