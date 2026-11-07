"""Workflow states and the only legal transitions between them."""

from enum import StrEnum


class TaskState(StrEnum):
    RECEIVED = "RECEIVED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    PATCH_PROPOSED = "PATCH_PROPOSED"
    VALIDATING = "VALIDATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    PR_CREATED = "PR_CREATED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ActorType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.REJECTED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.PR_CREATED,
    }
)


def is_terminal(state: TaskState) -> bool:
    """A terminal task accepts no further stage, decision, or delivery."""
    return state in TERMINAL_STATES


ALLOWED: dict[TaskState, set[TaskState]] = {
    TaskState.RECEIVED: {TaskState.TRIAGED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.TRIAGED: {TaskState.INVESTIGATING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.INVESTIGATING: {
        TaskState.PATCH_PROPOSED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.PATCH_PROPOSED: {
        TaskState.VALIDATING,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.VALIDATING: {
        TaskState.AWAITING_APPROVAL,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.AWAITING_APPROVAL: {
        TaskState.APPROVED,
        TaskState.REJECTED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.APPROVED: {TaskState.PR_CREATED, TaskState.FAILED},
    TaskState.PR_CREATED: set(),
    TaskState.REJECTED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


def actor_for(to_state: TaskState) -> ActorType:
    """The actor allowed to enter `to_state` from any legal predecessor."""
    if to_state is TaskState.FAILED:
        return ActorType.SYSTEM
    if to_state is TaskState.CANCELLED:
        return ActorType.HUMAN
    if to_state is TaskState.PR_CREATED:
        return ActorType.SYSTEM
    if to_state in {TaskState.APPROVED, TaskState.REJECTED}:
        return ActorType.HUMAN
    if to_state in {
        TaskState.TRIAGED,
        TaskState.INVESTIGATING,
        TaskState.PATCH_PROPOSED,
        TaskState.VALIDATING,
        TaskState.AWAITING_APPROVAL,
    }:
        return ActorType.AGENT
    raise ValueError(f"{to_state.value} is not a transition target.")
