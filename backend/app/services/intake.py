"""Persist an addressed issue as RECEIVED, or describe a decision command.

Intake writes tasks only through StateMachine. A missing repository stays
RECEIVED. One non-terminal task is active per room. Replaying the same
`(room_id, message_id)` returns that task. The default ref is `main`.

Decision commands are recognized here and are not applied: approval and cancel
services arrive in a later phase. No socket, model, Docker, or dossier.
"""

from dataclasses import dataclass
from typing import Literal

from app.agent.parser import ParsedCommand, ParsedIssue, ParsedMessage, ParseKind, parse_message
from app.domain.errors import TaskNotFound
from app.domain.models import Task
from app.domain.states import TaskState
from app.persistence.db import connect, utc_now
from app.persistence.repository import StateMachine

Outcome = Literal[
    "ignored",
    "needs_issue",
    "created",
    "needs_repository",
    "replayed",
    "repository_filled",
    "active_task",
    "usage",
    "task_not_found",
    "command",
]

_USAGE = {
    "approve": "Send approve <task_id>.",
    "reject": "Send reject <task_id> <reason>.",
    "cancel": "Send cancel <task_id>.",
}


@dataclass(frozen=True)
class IntakeResult:
    outcome: Outcome
    task: Task | None = None
    reply: str | None = None
    logs_truncated: bool = False
    error_code: str | None = None
    command: ParsedCommand | None = None


class IntakeService:
    """Create at most one active task for an addressed room message."""

    def __init__(self, machine: StateMachine, *, agent_id: str) -> None:
        if agent_id.strip() == "":
            raise ValueError("agent_id is required.")
        self._machine = machine
        self._agent_id = agent_id

    def receive(
        self,
        *,
        room_id: str,
        message_id: str,
        text: str,
        sender_id: str,
        sender_name: str,
    ) -> IntakeResult:
        """Accept one room message. The reply is text; nothing is posted to a socket."""
        room = room_id.strip()
        message = message_id.strip()
        sender = sender_id.strip()
        if room == "" or message == "" or sender == "" or sender_name.strip() == "":
            raise ValueError("Room, message, and sender are required.")
        if sender == self._agent_id:
            return IntakeResult(outcome="ignored")

        parsed = parse_message(text)
        if parsed.kind is ParseKind.NOT_ADDRESSED:
            return IntakeResult(outcome="ignored")
        if parsed.kind is ParseKind.COMMAND:
            assert parsed.command is not None
            return self._command(parsed.command)
        if parsed.kind is ParseKind.EMPTY or parsed.issue is None:
            return IntakeResult(
                outcome="needs_issue",
                reply="Send the issue and the repository.",
            )

        existing = self._machine.get_by_origin(room, message)
        if existing is not None:
            return self._replay(existing)

        active = self._machine.get_active_task(room)
        if active is not None:
            if _can_fill_repository(active, parsed.issue):
                return self._fill_repository(active, parsed.issue)
            return IntakeResult(
                outcome="active_task",
                task=active,
                reply=(
                    f"Task {active.id} is already active. Cancel that task or wait."
                ),
            )

        if parsed.issue.description == "":
            return IntakeResult(
                outcome="needs_issue",
                reply="Send the issue and the repository.",
            )
        return self._create(room, message, parsed.issue)

    def _command(self, command: ParsedCommand) -> IntakeResult:
        if command.task_token is None:
            return IntakeResult(
                outcome="usage",
                reply=_USAGE[command.name.value],
                command=command,
            )
        if command.task_id is None:
            missing = TaskNotFound(command.task_token)
            return IntakeResult(
                outcome="task_not_found",
                reply=f"task_not_found: {missing.message}",
                error_code=missing.code,
                command=command,
            )
        task = self._machine.find_task(command.task_id)
        if task is None:
            missing = TaskNotFound(command.task_id)
            return IntakeResult(
                outcome="task_not_found",
                reply=f"task_not_found: {missing.message}",
                error_code=missing.code,
                command=command,
            )
        if command.name.value == "reject" and command.reason is None:
            return IntakeResult(
                outcome="usage",
                task=task,
                reply=_USAGE["reject"],
                command=command,
            )
        # The parsed command is the record a later decider applies. This phase
        # does not write an approval row or move state.
        return IntakeResult(
            outcome="command",
            task=task,
            reply=f"Received {command.name.value} for task {task.id}.",
            command=command,
        )

    def _replay(self, task: Task) -> IntakeResult:
        if task.repository:
            reply = f"Task {task.id} is {task.state.value}."
        else:
            reply = _repository_request(task)
        return IntakeResult(outcome="replayed", task=task, reply=reply)

    def _fill_repository(self, task: Task, issue: ParsedIssue) -> IntakeResult:
        assert issue.repository is not None
        git_ref = issue.git_ref if issue.ref_explicit else task.git_ref
        self._write_repository(task.id, issue.repository, git_ref)
        stored = self._machine.get_task(task.id)
        if not stored.repository:
            return IntakeResult(
                outcome="active_task",
                task=stored,
                reply=f"Task {stored.id} is already active. Cancel that task or wait.",
            )
        return IntakeResult(
            outcome="repository_filled",
            task=stored,
            reply=(
                f"Task {stored.id} is RECEIVED. Repository set to {stored.repository}. "
                f"Ref is {stored.git_ref}."
            ),
        )

    def _write_repository(self, task_id: str, repository: str, git_ref: str) -> None:
        """Fill repository and ref on a RECEIVED row. State is not a column we write."""
        conn = connect(self._machine.database_path, busy_timeout_ms=2000)
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    UPDATE task
                    SET repository = ?, git_ref = ?, updated_at = ?
                    WHERE id = ? AND state = ?
                      AND (repository IS NULL OR trim(repository) = '')
                    """,
                    (repository, git_ref, utc_now(), task_id, TaskState.RECEIVED.value),
                )
                if cursor.rowcount != 1:
                    conn.rollback()
                    return
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

    def _create(self, room_id: str, message_id: str, issue: ParsedIssue) -> IntakeResult:
        task = self._machine.create_task(
            switch_room_id=room_id,
            origin_message_id=message_id,
            title=issue.title,
            description=issue.description,
            logs=issue.logs,
            repository=issue.repository,
            git_ref=issue.git_ref,
        )
        truncated = issue.logs_truncated
        if task.repository:
            reply = f"Task {task.id} is RECEIVED."
            outcome: Outcome = "created"
        else:
            reply = _repository_request(task)
            outcome = "needs_repository"
        if truncated:
            reply = f"{reply} Logs were truncated to the first 64 KiB."
        return IntakeResult(
            outcome=outcome,
            task=task,
            reply=reply,
            logs_truncated=truncated,
        )


def _can_fill_repository(task: Task, issue: ParsedIssue) -> bool:
    if task.state != TaskState.RECEIVED:
        return False
    if task.repository:
        return False
    return bool(issue.repository)


def _repository_request(task: Task) -> str:
    return (
        f"Task {task.id} is RECEIVED. Send the repository "
        "(Repo: https://github.com/<owner>/<repo>)."
    )
