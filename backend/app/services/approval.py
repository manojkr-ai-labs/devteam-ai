"""Human approval, rejection, and cancellation.

``decide`` requires a reviewer id that is not the agent and is in the
participant list for the task's room. The listener calls ``handle`` for
approve, reject, and cancel. An empty ``GITHUB_DELIVERY_TOKEN`` tells the
room that pull-request creation is not configured and does not call GitHub.
"""

import os
from collections.abc import Callable, Mapping, Sequence

from app.agent.parser import CommandName, ParsedCommand
from app.domain.errors import DomainError, InvalidTransition
from app.domain.models import Actor, Task
from app.domain.states import ALLOWED, ActorType, TaskState
from app.persistence.repository import StateMachine

_NOT_CONFIGURED = "Pull-request creation is not configured."
_USAGE = {
    CommandName.APPROVE: "Send approve <task_id>.",
    CommandName.REJECT: "Send reject <task_id> <reason>.",
    CommandName.CANCEL: "Send cancel <task_id>.",
}
ParticipantSource = Callable[[str], Sequence[object]]


class ApprovalService:
    """Record one human decision and let the listener post the room reply."""

    def __init__(
        self,
        machine: StateMachine,
        *,
        agent_id: str,
        participants: ParticipantSource,
    ) -> None:
        if agent_id.strip() == "":
            raise ValueError("agent_id is required.")
        self._machine = machine
        self._agent_id = agent_id.strip()
        self._participants = participants

    def decide(
        self,
        task_id: str,
        decision: str,
        reviewer: Actor | None,
        *,
        switch_message_id: str,
        reason: str | None = None,
        room_id: str | None = None,
    ) -> Task:
        """Approve or reject once. A refused call leaves the database unchanged."""
        task = self._load(task_id, room_id)
        reviewer = self._require_reviewer(reviewer, task)
        target = _decision_state(decision, task_id=task.id)
        _require_edge(task, target)
        stored_reason = _clean(reason)
        if target is TaskState.REJECTED and stored_reason is None:
            raise DomainError("Rejection requires a reason.", task_id=task.id)
        return self._machine.transition(
            task.id,
            target,
            reviewer,
            switch_message_id=switch_message_id,
            reason=stored_reason,
        )

    def cancel(
        self,
        task_id: str,
        reviewer: Actor | None,
        *,
        switch_message_id: str | None = None,
        room_id: str | None = None,
    ) -> Task:
        """Cancel from a legal state. This does not write an approval row."""
        task = self._load(task_id, room_id)
        reviewer = self._require_reviewer(reviewer, task)
        _require_edge(task, TaskState.CANCELLED)
        payload: dict[str, object] = {}
        message_id = _clean(switch_message_id)
        if message_id is not None:
            payload["switch_message_id"] = message_id
        return self._machine.transition(
            task.id,
            TaskState.CANCELLED,
            reviewer,
            payload=payload,
        )

    def handle(
        self,
        command: ParsedCommand,
        *,
        room_id: str,
        message_id: str,
        sender_id: str,
        sender_name: str,
    ) -> str | None:
        """Apply one listener command and return the room reply."""
        try:
            return self._handle(
                command,
                room_id=room_id,
                message_id=message_id,
                sender_id=sender_id,
                sender_name=sender_name,
            )
        except DomainError as exc:
            return f"{exc.code}: {exc.message}"

    def _handle(
        self,
        command: ParsedCommand,
        *,
        room_id: str,
        message_id: str,
        sender_id: str,
        sender_name: str,
    ) -> str:
        if command.task_id is None:
            if command.task_token is None:
                return _USAGE[command.name]
            return f"task_not_found: Task {command.task_token} was not found."
        if command.name is CommandName.REJECT and _clean(command.reason) is None:
            return _USAGE[CommandName.REJECT]
        reviewer = Actor(
            type=ActorType.HUMAN,
            id=sender_id.strip(),
            name=sender_name.strip() or sender_id.strip(),
        )
        if command.name is CommandName.APPROVE:
            task = self.decide(
                command.task_id,
                "approved",
                reviewer,
                switch_message_id=message_id,
                room_id=room_id,
            )
            if _delivery_token() == "":
                return _NOT_CONFIGURED
            return f"Task {task.id} is APPROVED."
        if command.name is CommandName.REJECT:
            self.decide(
                command.task_id,
                "rejected",
                reviewer,
                switch_message_id=message_id,
                reason=command.reason,
                room_id=room_id,
            )
            return command.reason.strip() if command.reason else ""
        task = self.cancel(
            command.task_id,
            reviewer,
            switch_message_id=message_id,
            room_id=room_id,
        )
        return f"Task {task.id} is CANCELLED."

    def _load(self, task_id: str, room_id: str | None) -> Task:
        task = self._machine.get_task(task_id)
        if room_id is not None and task.switch_room_id != room_id.strip():
            raise DomainError(
                "The reviewer is not a human participant in the room.",
                task_id=task.id,
            )
        return task

    def _require_reviewer(self, reviewer: Actor | None, task: Task) -> Actor:
        if reviewer is None or reviewer.id.strip() == "":
            raise DomainError("A decision requires a reviewer.", task_id=task.id)
        reviewer_id = reviewer.id.strip()
        if reviewer_id == self._agent_id:
            raise DomainError("The reviewer must not be the agent.", task_id=task.id)
        room = task.switch_room_id
        member_ids = _participant_ids(self._participants(room))
        if reviewer.type is not ActorType.HUMAN or reviewer_id not in member_ids:
            raise DomainError(
                "The reviewer is not a human participant in the room.",
                task_id=task.id,
            )
        return reviewer


def _delivery_token() -> str:
    return os.environ.get("GITHUB_DELIVERY_TOKEN", "").strip()


def _decision_state(decision: object, *, task_id: str) -> TaskState:
    if isinstance(decision, str):
        cleaned = decision.strip().lower()
        if cleaned == "approved":
            return TaskState.APPROVED
        if cleaned == "rejected":
            return TaskState.REJECTED
    raise DomainError("A decision must be approved or rejected.", task_id=task_id)


def _require_edge(task: Task, to_state: TaskState) -> None:
    if to_state in ALLOWED[task.state]:
        return
    raise InvalidTransition(
        f"Cannot move task {task.id} from {task.state.value} to {to_state.value}.",
        task_id=task.id,
        from_state=task.state,
        to_state=to_state,
    )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    return stripped


def _participant_ids(participants: Sequence[object]) -> set[str]:
    ids: set[str] = set()
    for item in participants:
        participant_id = _participant_id(item)
        if participant_id:
            ids.add(participant_id)
    return ids


def _participant_id(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, Mapping):
        raw = item.get("id")
        if isinstance(raw, str):
            return raw.strip()
        return ""
    raw_attr = getattr(item, "id", None)
    if isinstance(raw_attr, str):
        return raw_attr.strip()
    return ""
