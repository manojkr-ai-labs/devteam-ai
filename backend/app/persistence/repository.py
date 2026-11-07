"""The only writer of ``task.state``.

Every accepted change compares the current state, writes the stage rows, appends
one workflow event, and updates the task in a single transaction. An illegal
edge writes nothing.
"""

import json
import logging
import sqlite3
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, NoReturn, TypeVar
from uuid import UUID, uuid4

from app.domain.errors import ApprovalRequired, InvalidTransition, PersistenceError, TaskNotFound
from app.domain.models import (
    PRIORITIES,
    Actor,
    Approval,
    Finding,
    FindingDraft,
    FindingEvidence,
    Patch,
    PatchDraft,
    PullRequest,
    PullRequestSpec,
    Task,
    ValidationDraft,
    ValidationRun,
    WorkflowEvent,
)
from app.domain.paths import is_repo_relative_path
from app.domain.states import ALLOWED, TERMINAL_STATES, ActorType, TaskState, actor_for
from app.persistence.db import connect, init_db, utc_now

logger = logging.getLogger("devteam.state_machine")
_T = TypeVar("_T")
_TERMINAL_SQL = ", ".join(
    f"'{state.value}'" for state in sorted(TERMINAL_STATES, key=lambda item: item.value)
)


@dataclass(frozen=True)
class _TransitionInput:
    payload: Mapping[str, object]
    classification: str | None
    priority: str | None
    summary: str | None
    finding: FindingDraft | None
    patch: PatchDraft | None
    apply_check: str | None
    validation: ValidationDraft | None
    switch_message_id: str | None
    reason: str | None
    pull_request: PullRequestSpec | None


class StateMachine:
    """Persist tasks and apply legal workflow transitions."""

    def __init__(
        self,
        database_path: str,
        *,
        agent_id: str,
        busy_timeout_ms: int = 2000,
        lock_attempts: int = 4,
    ) -> None:
        if agent_id.strip() == "":
            raise ValueError("agent_id is required.")
        if busy_timeout_ms < 0 or lock_attempts < 1:
            raise ValueError("Lock settings must allow at least one attempt.")
        self.database_path = database_path
        self._agent_id = agent_id
        self._busy_timeout_ms = busy_timeout_ms
        self._lock_attempts = lock_attempts
        init_db(database_path)

    def create_task(
        self,
        *,
        switch_room_id: str,
        origin_message_id: str,
        title: str,
        description: str,
        logs: str | None = None,
        repository: str | None = None,
        git_ref: str = "main",
        task_id: str | None = None,
    ) -> Task:
        """Insert a RECEIVED task. A repeated origin message returns the original row."""
        room_id = switch_room_id.strip()
        message_id = origin_message_id.strip()
        if room_id == "" or message_id == "":
            raise ValueError("Room id and origin message id are required.")
        clean_title = title.strip()
        clean_description = description.strip()
        if clean_title == "" or clean_description == "":
            raise ValueError("Title and description are required.")
        ref = git_ref.strip() or "main"
        repo = repository.strip() if repository else ""
        try:
            new_id = str(uuid4()) if task_id is None else str(UUID(task_id))
        except ValueError as exc:
            raise ValueError("task_id must be a UUID.") from exc
        try:
            return self._retry(
                lambda: self._insert_task(
                    task_id=new_id,
                    switch_room_id=room_id,
                    origin_message_id=message_id,
                    title=clean_title,
                    description=clean_description,
                    logs=logs,
                    repository=repo or None,
                    git_ref=ref,
                ),
                task_id=new_id,
            )
        except sqlite3.IntegrityError as exc:
            if "switch_room_id" not in str(exc):
                raise
            existing = self.get_by_origin(room_id, message_id)
            if existing is None:
                raise
            logger.info(
                "duplicate_origin task_id=%s room_id=%s message_id=%s",
                existing.id,
                room_id,
                message_id,
            )
            return existing

    def get_task(self, task_id: str) -> Task:
        task = self.find_task(task_id)
        if task is None:
            raise TaskNotFound(task_id)
        return task

    def find_task(self, task_id: str) -> Task | None:
        row = self._read_one("SELECT * FROM task WHERE id = ?", (task_id,))
        return None if row is None else _task_from_row(row)

    def get_by_origin(self, switch_room_id: str, origin_message_id: str) -> Task | None:
        row = self._read_one(
            "SELECT * FROM task WHERE switch_room_id = ? AND origin_message_id = ?",
            (switch_room_id, origin_message_id),
        )
        return None if row is None else _task_from_row(row)

    def get_active_task(self, switch_room_id: str) -> Task | None:
        """The newest non-terminal task in the room, if one exists."""
        row = self._read_one(
            f"""
            SELECT * FROM task
            WHERE switch_room_id = ? AND state NOT IN ({_TERMINAL_SQL})
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (switch_room_id,),
        )
        return None if row is None else _task_from_row(row)

    def list_tasks(self) -> list[Task]:
        rows = self._read_all("SELECT * FROM task ORDER BY created_at DESC, id DESC")
        return [_task_from_row(row) for row in rows]

    def list_events(self, task_id: str) -> list[WorkflowEvent]:
        rows = self._read_all(
            "SELECT * FROM workflow_event WHERE task_id = ? ORDER BY created_at ASC, id ASC",
            (task_id,),
        )
        return [_event_from_row(row) for row in rows]

    def get_finding(self, task_id: str) -> Finding | None:
        row = self._read_one(
            "SELECT * FROM finding WHERE task_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (task_id,),
        )
        if row is None:
            return None
        evidence_rows = self._read_all(
            """
            SELECT * FROM finding_evidence
            WHERE finding_id = ?
            ORDER BY start_line ASC, path ASC, id ASC
            """,
            (str(row["id"]),),
        )
        evidence = [FindingEvidence.model_validate(_as_dict(item)) for item in evidence_rows]
        data = _as_dict(row)
        data["evidence"] = evidence
        return Finding.model_validate(data)

    def get_patch(self, task_id: str) -> Patch | None:
        row = self._read_one("SELECT * FROM patch WHERE task_id = ?", (task_id,))
        if row is None:
            return None
        data = _as_dict(row)
        data["affected_files"] = _json_str_list(data["affected_files"])
        data["test_recommendations"] = _json_str_list(data["test_recommendations"])
        return Patch.model_validate(data)

    def list_validation_runs(self, task_id: str) -> list[ValidationRun]:
        rows = self._read_all(
            """
            SELECT * FROM validation_run
            WHERE task_id = ?
            ORDER BY started_at ASC, id ASC
            """,
            (task_id,),
        )
        return [ValidationRun.model_validate(_as_dict(row)) for row in rows]

    def get_approval(self, task_id: str) -> Approval | None:
        row = self._read_one("SELECT * FROM approval WHERE task_id = ?", (task_id,))
        return None if row is None else Approval.model_validate(_as_dict(row))

    def get_pull_request(self, task_id: str) -> PullRequest | None:
        row = self._read_one("SELECT * FROM pull_request WHERE task_id = ?", (task_id,))
        return None if row is None else PullRequest.model_validate(_as_dict(row))

    def fail(self, task_id: str, *, stage: str, error: str, actor: Actor) -> Task:
        """Move a non-terminal task to FAILED with the stage name and error in the event."""
        return self.transition(
            task_id,
            TaskState.FAILED,
            actor,
            payload={"stage": stage, "error": error},
        )

    def transition(
        self,
        task_id: str,
        to_state: TaskState,
        actor: Actor,
        *,
        payload: Mapping[str, object] | None = None,
        classification: str | None = None,
        priority: str | None = None,
        summary: str | None = None,
        finding: FindingDraft | None = None,
        patch: PatchDraft | None = None,
        apply_check: str | None = None,
        validation: ValidationDraft | None = None,
        switch_message_id: str | None = None,
        reason: str | None = None,
        pull_request: PullRequestSpec | None = None,
    ) -> Task:
        """Apply one legal transition.

        Invalid attempts leave the row and the event log unchanged.
        """
        data = _TransitionInput(
            payload={} if payload is None else payload,
            classification=classification,
            priority=priority,
            summary=summary,
            finding=finding,
            patch=patch,
            apply_check=apply_check,
            validation=validation,
            switch_message_id=switch_message_id,
            reason=reason,
            pull_request=pull_request,
        )
        return self._retry(
            lambda: self._transition_once(task_id, to_state, actor, data),
            task_id=task_id,
        )

    def _transition_once(
        self,
        task_id: str,
        to_state: TaskState,
        actor: Actor,
        data: _TransitionInput,
    ) -> Task:
        conn = self._connect()
        try:
            with _immediate(conn):
                row = _fetch_one(conn, "SELECT * FROM task WHERE id = ?", (task_id,))
                if row is None:
                    raise TaskNotFound(task_id)
                current = TaskState(str(row["state"]))
                self._ensure_edge(task_id, current, to_state, actor)
                now = utc_now()
                event_payload = self._prepare(
                    conn, row, task_id, current, to_state, actor, data, now
                )
                _insert_event(
                    conn,
                    event_id=str(uuid4()),
                    task_id=task_id,
                    from_state=current,
                    to_state=to_state,
                    actor=actor,
                    payload=event_payload,
                    created_at=now,
                )
                conn.execute(
                    "UPDATE task SET state = ?, updated_at = ? WHERE id = ?",
                    (to_state.value, now, task_id),
                )
                stored = _fetch_one(conn, "SELECT * FROM task WHERE id = ?", (task_id,))
                if stored is None:
                    raise TaskNotFound(task_id)
                return _task_from_row(stored)
        finally:
            conn.close()

    def _prepare(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
        data: _TransitionInput,
        now: str,
    ) -> dict[str, Any]:
        event_payload: dict[str, Any] = dict(data.payload)
        if to_state is TaskState.TRIAGED:
            self._apply_triage(conn, task_id, current, to_state, actor, data, event_payload)
        elif to_state is TaskState.INVESTIGATING:
            self._require_repository(row, task_id, current, to_state, actor)
        elif to_state is TaskState.PATCH_PROPOSED:
            self._apply_patch(conn, task_id, current, to_state, actor, data, now)
        elif to_state is TaskState.VALIDATING:
            self._record_apply_check(task_id, current, to_state, actor, data, event_payload)
        elif to_state is TaskState.AWAITING_APPROVAL:
            self._apply_validation(
                conn, task_id, current, to_state, actor, data, event_payload, now
            )
        elif to_state in {TaskState.APPROVED, TaskState.REJECTED}:
            self._apply_decision(conn, task_id, current, to_state, actor, data, event_payload, now)
        elif to_state is TaskState.PR_CREATED:
            self._apply_pull_request(
                conn, row, task_id, current, to_state, actor, data, event_payload, now
            )
        elif to_state is TaskState.FAILED:
            self._require_failure(task_id, current, to_state, actor, event_payload)
        return event_payload

    def _ensure_edge(
        self,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
    ) -> None:
        if to_state not in ALLOWED[current]:
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                f"Cannot move task {task_id} from {current.value} to {to_state.value}.",
            )
        expected = actor_for(to_state)
        if actor.type != expected:
            article = "an" if expected is ActorType.AGENT else "a"
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                f"This transition requires {article} {expected.value} actor.",
            )

    def _apply_triage(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
        data: _TransitionInput,
        event_payload: dict[str, Any],
    ) -> None:
        classification = (data.classification or "").strip()
        summary = (data.summary or "").strip()
        priority = data.priority
        if classification == "" or priority not in PRIORITIES or summary == "":
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                "Triage requires classification, priority, and a summary.",
            )
        conn.execute(
            "UPDATE task SET classification = ?, priority = ?, summary = ? WHERE id = ?",
            (classification, priority, summary, task_id),
        )
        event_payload["classification"] = classification
        event_payload["priority"] = priority
        event_payload["summary"] = summary

    def _require_repository(
        self,
        row: sqlite3.Row,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
    ) -> None:
        repository = row["repository"]
        if not isinstance(repository, str) or repository.strip() == "":
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                "Investigation requires a repository reference.",
            )

    def _apply_patch(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
        data: _TransitionInput,
        now: str,
    ) -> None:
        finding = data.finding
        patch = data.patch
        if finding is None or patch is None:
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                "A patch requires stored findings and a diff.",
            )
        paths = [item.path for item in finding.evidence]
        paths.extend(patch.affected_files)
        if any(not is_repo_relative_path(path) for path in paths):
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                "A cited path must stay inside the repository.",
            )
        finding_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO finding (
                id, task_id, hypothesis, summary, recommended_action, uncertainties, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                task_id,
                finding.hypothesis,
                finding.summary,
                finding.recommended_action,
                finding.uncertainties,
                now,
            ),
        )
        for item in finding.evidence:
            conn.execute(
                """
                INSERT INTO finding_evidence (
                    id, finding_id, path, start_line, end_line, excerpt, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    finding_id,
                    item.path,
                    item.start_line,
                    item.end_line,
                    item.excerpt,
                    item.reason,
                ),
            )
        conn.execute(
            """
            INSERT INTO patch (
                id, task_id, diff, summary, affected_files, test_recommendations, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                task_id,
                patch.diff,
                patch.summary,
                json.dumps(patch.affected_files),
                json.dumps(patch.test_recommendations),
                now,
            ),
        )

    def _record_apply_check(
        self,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
        data: _TransitionInput,
        event_payload: dict[str, Any],
    ) -> None:
        if data.apply_check is None:
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                "Validation requires a successful git apply --check.",
            )
        event_payload["apply_check"] = data.apply_check

    def _apply_validation(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
        data: _TransitionInput,
        event_payload: dict[str, Any],
        now: str,
    ) -> None:
        draft = data.validation
        if draft is None:
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                "Approval requires a stored validation run.",
            )
        status = "passed" if draft.exit_code == 0 else "failed"
        started_at = draft.started_at or now
        finished_at = draft.finished_at or now
        conn.execute(
            """
            INSERT INTO validation_run (
                id, task_id, command, exit_code, stdout, stderr, status, risks,
                started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                task_id,
                draft.command,
                draft.exit_code,
                draft.stdout,
                draft.stderr,
                status,
                draft.risks,
                started_at,
                finished_at,
            ),
        )
        event_payload["command"] = draft.command
        event_payload["exit_code"] = draft.exit_code
        event_payload["status"] = status

    def _apply_decision(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
        data: _TransitionInput,
        event_payload: dict[str, Any],
        now: str,
    ) -> None:
        message_id = (data.switch_message_id or "").strip()
        if message_id == "":
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                "A decision requires the Switch message id.",
            )
        stored_reason = data.reason.strip() if data.reason and data.reason.strip() else None
        decision = "approved" if to_state is TaskState.APPROVED else "rejected"
        if decision == "rejected" and stored_reason is None:
            self._refuse(task_id, current, to_state, actor, "Rejection requires a reason.")
        conn.execute(
            """
            INSERT INTO approval (
                id, task_id, decision, reviewer_id, reviewer_name,
                switch_message_id, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                task_id,
                decision,
                actor.id,
                actor.name,
                message_id,
                stored_reason,
                now,
            ),
        )
        event_payload["decision"] = decision
        event_payload["switch_message_id"] = message_id
        if stored_reason is not None:
            event_payload["reason"] = stored_reason

    def _apply_pull_request(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
        data: _TransitionInput,
        event_payload: dict[str, Any],
        now: str,
    ) -> None:
        approval = _fetch_one(conn, "SELECT * FROM approval WHERE task_id = ?", (task_id,))
        if approval is None or str(approval["decision"]) != "approved":
            self._refuse_approval(
                task_id,
                actor,
                "A pull request requires a stored human approval.",
            )
        if str(approval["reviewer_id"]) == self._agent_id:
            self._refuse_approval(
                task_id,
                actor,
                "An approval recorded by the agent cannot authorize delivery.",
            )
        spec = data.pull_request
        if spec is None:
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                "Pull-request creation requires the GitHub URL and number.",
            )
        expected_branch = f"devteam/{task_id}"
        if spec.head_branch != expected_branch:
            self._refuse(
                task_id,
                current,
                to_state,
                actor,
                f"The pull-request branch must be {expected_branch}.",
            )
        base_ref = str(row["git_ref"])
        conn.execute(
            """
            INSERT INTO pull_request (
                id, task_id, url, number, head_branch, base_ref, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), task_id, spec.url, spec.number, spec.head_branch, base_ref, now),
        )
        event_payload["url"] = spec.url
        event_payload["number"] = spec.number
        event_payload["head_branch"] = spec.head_branch
        event_payload["base_ref"] = base_ref

    def _require_failure(
        self,
        task_id: str,
        current: TaskState,
        to_state: TaskState,
        actor: Actor,
        event_payload: dict[str, Any],
    ) -> None:
        stage = event_payload.get("stage")
        error = event_payload.get("error")
        if not isinstance(stage, str) or stage.strip() == "":
            self._refuse(task_id, current, to_state, actor, "A failure record needs a stage.")
        if not isinstance(error, str) or error.strip() == "":
            self._refuse(task_id, current, to_state, actor, "A failure record needs an error.")
        event_payload["stage"] = stage.strip()
        event_payload["error"] = error.strip()

    def _refuse(
        self,
        task_id: str,
        from_state: TaskState,
        to_state: TaskState,
        actor: Actor,
        detail: str,
    ) -> NoReturn:
        logger.warning(
            "invalid_transition task_id=%s from_state=%s to_state=%s "
            "actor_type=%s actor_id=%s detail=%s",
            task_id,
            from_state.value,
            to_state.value,
            actor.type.value,
            actor.id,
            detail,
        )
        raise InvalidTransition(detail, task_id=task_id, from_state=from_state, to_state=to_state)

    def _refuse_approval(self, task_id: str, actor: Actor, detail: str) -> NoReturn:
        logger.warning(
            "approval_required task_id=%s actor_type=%s actor_id=%s detail=%s",
            task_id,
            actor.type.value,
            actor.id,
            detail,
        )
        raise ApprovalRequired(detail, task_id=task_id)

    def _insert_task(
        self,
        *,
        task_id: str,
        switch_room_id: str,
        origin_message_id: str,
        title: str,
        description: str,
        logs: str | None,
        repository: str | None,
        git_ref: str,
    ) -> Task:
        now = utc_now()
        conn = self._connect()
        try:
            with _immediate(conn):
                conn.execute(
                    """
                    INSERT INTO task (
                        id, switch_room_id, origin_message_id, repository, git_ref,
                        title, description, logs, classification, priority, summary,
                        state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)
                    """,
                    (
                        task_id,
                        switch_room_id,
                        origin_message_id,
                        repository,
                        git_ref,
                        title,
                        description,
                        logs,
                        TaskState.RECEIVED.value,
                        now,
                        now,
                    ),
                )
                stored = _fetch_one(conn, "SELECT * FROM task WHERE id = ?", (task_id,))
                if stored is None:
                    raise TaskNotFound(task_id)
                return _task_from_row(stored)
        finally:
            conn.close()

    def _retry(self, operation: Callable[[], _T], *, task_id: str | None) -> _T:
        delay_s = 0.02
        for attempt in range(1, self._lock_attempts + 1):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                if not _is_lock_error(exc) or attempt == self._lock_attempts:
                    if _is_lock_error(exc):
                        logger.error("persistence_error task_id=%s error=%s", task_id, exc)
                        raise PersistenceError(
                            "The task state could not be saved because the database was locked.",
                            task_id=task_id,
                        ) from exc
                    raise
                time.sleep(delay_s)
                delay_s *= 2
        raise PersistenceError(
            "The task state could not be saved because the database was locked.",
            task_id=task_id,
        )

    def _connect(self) -> sqlite3.Connection:
        return connect(self.database_path, busy_timeout_ms=self._busy_timeout_ms)

    def _read_one(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        conn = self._connect()
        try:
            return _fetch_one(conn, sql, params)
        finally:
            conn.close()

    def _read_all(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            return list(conn.execute(sql, params))
        finally:
            conn.close()


@contextmanager
def _immediate(conn: sqlite3.Connection) -> Iterator[None]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _fetch_one(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[object, ...],
) -> sqlite3.Row | None:
    row = conn.execute(sql, params).fetchone()
    return row if isinstance(row, sqlite3.Row) else None


def _insert_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    task_id: str,
    from_state: TaskState,
    to_state: TaskState,
    actor: Actor,
    payload: Mapping[str, Any],
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO workflow_event (
            id, task_id, from_state, to_state, actor_type, actor_id, actor_name, payload, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            task_id,
            from_state.value,
            to_state.value,
            actor.type.value,
            actor.id,
            actor.name,
            json.dumps(dict(payload), sort_keys=True, separators=(",", ":")),
            created_at,
        ),
    )


def _as_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _task_from_row(row: sqlite3.Row) -> Task:
    return Task.model_validate(_as_dict(row))


def _event_from_row(row: sqlite3.Row) -> WorkflowEvent:
    data = _as_dict(row)
    raw = data["payload"]
    if not isinstance(raw, str):
        raise PersistenceError(
            "A workflow event payload is not valid JSON.",
            task_id=str(data["task_id"]),
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PersistenceError(
            "A workflow event payload is not valid JSON.",
            task_id=str(data["task_id"]),
        ) from exc
    if not isinstance(parsed, dict):
        raise PersistenceError(
            "A workflow event payload is not valid JSON.",
            task_id=str(data["task_id"]),
        )
    data["payload"] = parsed
    return WorkflowEvent.model_validate(data)


def _json_str_list(raw: object) -> list[str]:
    if not isinstance(raw, str):
        raise TypeError("Expected a JSON list of strings.")
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise TypeError("Expected a JSON list of strings.")
    return parsed


def _is_lock_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message
