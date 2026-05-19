"""SQLite storage engine for agent-bank memories."""

import json
import sqlite3
from pathlib import Path

from agent_bank.models import Memory

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'preference',
    scope TEXT NOT NULL DEFAULT 'global',
    subject TEXT,
    source TEXT NOT NULL DEFAULT 'user_stated',
    importance REAL NOT NULL DEFAULT 0.5,
    tags TEXT NOT NULL DEFAULT '[]',
    project TEXT,
    timeline TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed TEXT,
    access_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_memories_subject ON memories(subject);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    """SQLite-backed storage for memories.

    Uses WAL mode for concurrent read access from multiple MCP clients.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        # Set schema version
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        conn.commit()

    def add(self, memory: Memory) -> Memory:
        """Insert a new memory."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO memories 
               (id, content, category, scope, subject, source, importance,
                tags, project, timeline, created_at, updated_at, 
                last_accessed, access_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                memory.id,
                memory.content,
                memory.category,
                memory.scope,
                memory.subject,
                memory.source,
                memory.importance,
                json.dumps(memory.tags, ensure_ascii=False),
                memory.project,
                json.dumps(memory.timeline, ensure_ascii=False),
                memory.created_at,
                memory.updated_at,
                memory.last_accessed,
                memory.access_count,
            ),
        )
        conn.commit()
        return memory

    def get(self, memory_id: str) -> Memory | None:
        """Get a memory by ID."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def update(self, memory: Memory) -> None:
        """Update an existing memory."""
        conn = self._get_conn()
        conn.execute(
            """UPDATE memories SET
               content=?, category=?, scope=?, subject=?, source=?,
               importance=?, tags=?, project=?, timeline=?,
               updated_at=?, last_accessed=?, access_count=?
               WHERE id=?""",
            (
                memory.content,
                memory.category,
                memory.scope,
                memory.subject,
                memory.source,
                memory.importance,
                json.dumps(memory.tags, ensure_ascii=False),
                memory.project,
                json.dumps(memory.timeline, ensure_ascii=False),
                memory.updated_at,
                memory.last_accessed,
                memory.access_count,
                memory.id,
            ),
        )
        conn.commit()

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if deleted."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        return cursor.rowcount > 0

    def search(
        self,
        query: str | None = None,
        category: str | None = None,
        scope: str | None = None,
        subject: str | None = None,
        project: str | None = None,
        top_k: int = 10,
    ) -> list[Memory]:
        """Search memories with filters.

        For v0.1: keyword matching via SQL LIKE.
        Future: vector search via sqlite-vec.
        """
        conn = self._get_conn()
        conditions = []
        params: list = []

        # Scope filtering
        if scope and scope != "all":
            conditions.append("scope = ?")
            params.append(scope)
        elif scope == "all" or scope is None:
            # Return global + current project's memories
            if project:
                conditions.append(
                    "(scope = 'global' OR (scope = 'project' AND project = ?))"
                )
                params.append(project)
            else:
                conditions.append("scope = 'global'")

        if category and category != "all":
            conditions.append("category = ?")
            params.append(category)

        if subject:
            conditions.append("subject = ?")
            params.append(subject)

        where = " AND ".join(conditions) if conditions else "1=1"

        # Keyword search via LIKE (v0.1 — will be replaced by vector search)
        if query:
            # Split query into keywords and match any
            keywords = [k.strip() for k in query.split() if k.strip()]
            if keywords:
                keyword_conditions = []
                for kw in keywords:
                    keyword_conditions.append("(content LIKE ? OR subject LIKE ? OR tags LIKE ?)")
                    params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
                where += " AND (" + " OR ".join(keyword_conditions) + ")"

        sql = f"""
            SELECT * FROM memories 
            WHERE {where}
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
        """
        params.append(top_k)

        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def get_all(self, category: str | None = None) -> list[Memory]:
        """Get all memories, optionally filtered by category."""
        conn = self._get_conn()
        if category:
            rows = conn.execute(
                "SELECT * FROM memories WHERE category = ? ORDER BY importance DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY category, importance DESC"
            ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def count(self) -> dict[str, int]:
        """Get memory counts by category."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM memories GROUP BY category"
        ).fetchall()
        result = {row["category"]: row["cnt"] for row in rows}
        result["total"] = sum(result.values())
        return result

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_memory(row: sqlite3.Row) -> Memory:
        """Convert a database row to a Memory object."""
        return Memory(
            id=row["id"],
            content=row["content"],
            category=row["category"],
            scope=row["scope"],
            subject=row["subject"],
            source=row["source"],
            importance=row["importance"],
            tags=json.loads(row["tags"]),
            project=row["project"],
            timeline=json.loads(row["timeline"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
        )
