"""Read a local checkout, then stay INVESTIGATING when no model is called.

Frames and route strings are read first, then search hits, then matching
functions and their callers, at most eight files. Excerpts stored on the
INVESTIGATING event are the file text that was read. A citation of any other
path is dropped. This stage does not invent a diff and does not open a socket.
"""

import inspect
import os
import re
from collections.abc import Sequence
from typing import Protocol

from app.agent.listener import RoomEvent, RoomListener, StageResult
from app.domain.models import Actor, FindingDraft, PatchDraft, Task
from app.domain.paths import is_repo_relative_path
from app.domain.states import ActorType, TaskState
from app.integrations.repository import FileRead, LocalRepository
from app.persistence.repository import StateMachine
from app.services.patch import PatchService

FILE_CAP = 8
_STAGE_OUTCOMES = frozenset({"created", "needs_repository", "repository_filled"})
_FRAME = re.compile(r'File "([^"]+)", line (\d+)(?:, in ([A-Za-z_][A-Za-z0-9_]*))?')
_ROUTE = re.compile(r"""["'](/(?:[A-Za-z0-9_.~{}-]+/)*[A-Za-z0-9_.~{}-]+)["']""")


class ReasoningPort(Protocol):
    """Optional model. Called only when a reasoning API key is set."""

    def hypothesize(self, *, issue: str, excerpts: Sequence[FileRead]) -> FindingDraft:
        """Return a hypothesis. Only `excerpts` may be cited."""
        ...

    def propose_patch(
        self,
        *,
        hypothesis: FindingDraft,
        files: Sequence[FileRead],
    ) -> PatchDraft:
        """Return one patch for `files`. The diff is the caller's."""
        ...


class InvestigationService:
    """Turn a RECEIVED issue into stored excerpts, and a patch only from a model."""

    def __init__(
        self,
        machine: StateMachine,
        repository: LocalRepository,
        *,
        agent_id: str,
        agent_name: str = "DevTeam",
        reasoning: ReasoningPort | None = None,
        reasoning_api_key: str | None = None,
    ) -> None:
        if agent_id.strip() == "":
            raise ValueError("agent_id is required.")
        self._machine = machine
        self._repository = repository
        self._agent = Actor(type=ActorType.AGENT, id=agent_id, name=agent_name)
        self._reasoning = reasoning
        self._key_override = reasoning_api_key
        self.patch = PatchService(
            machine,
            repository,
            agent_id=agent_id,
            agent_name=agent_name,
        )

    def run(self, task: Task) -> StageResult:
        """Intake's next stage. The reply is room text for the caller."""
        if not self._repository.resolve(task.repository, task.git_ref):
            return StageResult(
                reply=f"Task {task.id} is RECEIVED. The local checkout did not resolve."
            )
        self._retrieve(task)
        current = self._machine.get_task(task.id)
        if current.state == TaskState.RECEIVED:
            current = self._machine.transition(
                current.id,
                TaskState.TRIAGED,
                self._agent,
                classification="bug",
                priority="medium",
                summary=current.title,
            )
        if current.state == TaskState.TRIAGED:
            current = self._machine.transition(
                current.id,
                TaskState.INVESTIGATING,
                self._agent,
                payload={"excerpts": [_excerpt_payload(item) for item in self._repository.reads]},
            )
        if self._api_key() is None or self._reasoning is None:
            return StageResult(reply=_excerpt_reply(current.id, self._repository.reads))
        return self._from_model(current)

    def _retrieve(self, task: Task) -> None:
        text = _issue_text(task)
        functions: list[str] = []
        for path, _line, func in _FRAME.findall(text):
            self._read_capped(path)
            if func:
                functions.append(func)
        for route in _unique(_ROUTE.findall(text)):
            for path in self._repository.search(route):
                self._read_capped(path)
        for name in _unique(functions):
            for path in self._repository.search(f"def {name}"):
                self._read_capped(path)
            for path in self._repository.search(name):
                self._read_capped(path)

    def _read_capped(self, path: str) -> None:
        normalized = path.strip().replace("\\", "/")
        if not is_repo_relative_path(normalized):
            self._repository.read(path)
            return
        if len(self._repository.reads) >= FILE_CAP:
            return
        self._repository.read(normalized)

    def _from_model(self, task: Task) -> StageResult:
        reasoning = self._reasoning
        if reasoning is None:
            return StageResult(reply=_excerpt_reply(task.id, self._repository.reads))
        draft = reasoning.hypothesize(
            issue=_issue_text(task),
            excerpts=list(self._repository.reads),
        )
        grounded, dropped = self.patch.ground(draft)
        if grounded is None:
            reply = _excerpt_reply(task.id, self._repository.reads)
            if dropped:
                note = "Dropped citations that were not read: " + ", ".join(dropped)
                reply = f"{reply}\n{note}"
            return StageResult(reply=reply)
        proposed = reasoning.propose_patch(
            hypothesis=grounded,
            files=self.patch.files_for(grounded),
        )
        stored = self.patch.store(
            task,
            diff=proposed.diff,
            summary=proposed.summary,
            affected_files=list(proposed.affected_files),
            test_recommendations=list(proposed.test_recommendations),
            finding=grounded,
        )
        if stored.state == TaskState.FAILED:
            error = _failure_error(self._machine, stored.id)
            return StageResult(reply=f"Task {stored.id} is FAILED. {error}")
        if stored.state == TaskState.PATCH_PROPOSED:
            return StageResult(reply=f"Task {stored.id} is PATCH_PROPOSED.\n{proposed.summary}")
        return StageResult(reply=_excerpt_reply(stored.id, self._repository.reads))

    def _api_key(self) -> str | None:
        if self._key_override is not None:
            return self._key_override.strip() or None
        return os.environ.get("REASONING_API_KEY", "").strip() or None


def room_text_for(
    listener: RoomListener,
    *,
    message_id: str,
    text: str,
    sender_id: str,
    sender_name: str,
) -> str:
    """Run intake, then the listener's stage, and return the room text.

    The listener is not started. No socket is opened and nothing is posted.
    """
    message = RoomEvent(
        kind="message",
        room_id=listener._room_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        text=text,
        addressed=True,
    )
    if not listener._actionable(message):
        return ""
    reply, task, outcome = listener._accept(message)
    parts: list[str] = []
    if reply:
        parts.append(reply)
    stage = listener._stage
    if task is None or stage is None or outcome not in _STAGE_OUTCOMES:
        return "\n\n".join(parts)
    result = stage(task)
    if inspect.isawaitable(result):
        close = getattr(result, "close", None)
        if callable(close):
            close()
        raise TypeError("Investigation returns room text and does not open a socket.")
    if isinstance(result, StageResult) and result.reply:
        parts.append(result.reply)
    return "\n\n".join(parts)


def _issue_text(task: Task) -> str:
    parts = [task.title, task.description]
    if task.logs:
        parts.append(task.logs)
    return "\n\n".join(parts)


def _excerpt_payload(item: FileRead) -> dict[str, object]:
    return {
        "path": item.path,
        "start_line": item.start_line,
        "end_line": item.end_line,
        "excerpt": item.excerpt,
    }


def _excerpt_reply(task_id: str, reads: list[FileRead]) -> str:
    blocks = [f"Task {task_id} is INVESTIGATING."]
    for item in reads:
        blocks.append(f"{item.path}:{item.start_line}-{item.end_line}\n{item.excerpt}")
    return "\n".join(blocks)


def _failure_error(machine: StateMachine, task_id: str) -> str:
    events = machine.list_events(task_id)
    if not events:
        return "invalid_diff"
    error = events[-1].payload.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    return "invalid_diff"


def _unique(items: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
