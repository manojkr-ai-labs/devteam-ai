"""Domain contracts for tasks, evidence, and legal workflow transitions."""

from app.domain.errors import (
    ApprovalRequired,
    DomainError,
    InvalidTransition,
    NotAddressed,
    PersistenceError,
    TaskNotFound,
)
from app.domain.models import (
    Actor,
    Approval,
    Finding,
    FindingDraft,
    Patch,
    PatchDraft,
    PullRequest,
    PullRequestSpec,
    Task,
    ValidationDraft,
    ValidationRun,
    WorkflowEvent,
)
from app.domain.states import ALLOWED, ActorType, TaskState, actor_for, is_terminal

__all__ = [
    "ALLOWED",
    "Actor",
    "ActorType",
    "Approval",
    "ApprovalRequired",
    "DomainError",
    "Finding",
    "FindingDraft",
    "InvalidTransition",
    "NotAddressed",
    "Patch",
    "PatchDraft",
    "PersistenceError",
    "PullRequest",
    "PullRequestSpec",
    "Task",
    "TaskNotFound",
    "TaskState",
    "ValidationDraft",
    "ValidationRun",
    "WorkflowEvent",
    "actor_for",
    "is_terminal",
]
