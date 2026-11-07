"""SQLite schema and connections. Tables match the domain models."""

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from app.domain.models import DECISIONS, PRIORITIES, VALIDATION_STATUSES
from app.domain.states import ActorType, TaskState


def utc_now() -> str:
    """Current time as UTC ISO-8601 with a Z suffix. Never a local offset."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _literals(values: Iterable[str]) -> str:
    quoted: list[str] = []
    for value in values:
        if value == "" or "'" in value:
            raise ValueError(f"Refusing SQL literal {value!r}.")
        quoted.append(f"'{value}'")
    return ", ".join(quoted)


def schema_sql() -> str:
    states = _literals(state.value for state in TaskState)
    priorities = _literals(PRIORITIES)
    actors = _literals(actor.value for actor in ActorType)
    decisions = _literals(DECISIONS)
    statuses = _literals(VALIDATION_STATUSES)
    return f"""
    CREATE TABLE IF NOT EXISTS task (
        id TEXT PRIMARY KEY,
        switch_room_id TEXT NOT NULL,
        origin_message_id TEXT NOT NULL,
        repository TEXT,
        git_ref TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        logs TEXT,
        classification TEXT,
        priority TEXT CHECK (priority IS NULL OR priority IN ({priorities})),
        summary TEXT,
        state TEXT NOT NULL CHECK (state IN ({states})),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (switch_room_id, origin_message_id)
    );

    CREATE TABLE IF NOT EXISTS workflow_event (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES task(id),
        from_state TEXT NOT NULL CHECK (from_state IN ({states})),
        to_state TEXT NOT NULL CHECK (to_state IN ({states})),
        actor_type TEXT NOT NULL CHECK (actor_type IN ({actors})),
        actor_id TEXT NOT NULL,
        actor_name TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS finding (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES task(id),
        hypothesis TEXT NOT NULL,
        summary TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        uncertainties TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS finding_evidence (
        id TEXT PRIMARY KEY,
        finding_id TEXT NOT NULL REFERENCES finding(id),
        path TEXT NOT NULL,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL,
        excerpt TEXT NOT NULL,
        reason TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS patch (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL UNIQUE REFERENCES task(id),
        diff TEXT NOT NULL,
        summary TEXT NOT NULL,
        affected_files TEXT NOT NULL,
        test_recommendations TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS validation_run (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES task(id),
        command TEXT NOT NULL,
        exit_code INTEGER,
        stdout TEXT NOT NULL,
        stderr TEXT NOT NULL,
        status TEXT CHECK (status IS NULL OR status IN ({statuses})),
        risks TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT
    );

    CREATE TABLE IF NOT EXISTS approval (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL UNIQUE REFERENCES task(id),
        decision TEXT NOT NULL CHECK (decision IN ({decisions})),
        reviewer_id TEXT NOT NULL,
        reviewer_name TEXT NOT NULL,
        switch_message_id TEXT NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pull_request (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL UNIQUE REFERENCES task(id),
        url TEXT NOT NULL,
        number INTEGER NOT NULL,
        head_branch TEXT NOT NULL,
        base_ref TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_task_room_state ON task (switch_room_id, state);
    CREATE INDEX IF NOT EXISTS idx_event_task ON workflow_event (task_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_finding_task ON finding (task_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_validation_task ON validation_run (task_id, started_at);
    """


def connect(path: str, *, busy_timeout_ms: int) -> sqlite3.Connection:
    timeout_s = busy_timeout_ms / 1000
    conn = sqlite3.connect(path, timeout=timeout_s, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    return conn


def init_db(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path, busy_timeout_ms=2000)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(schema_sql())
    finally:
        conn.close()
