"""Errors the workflow returns. Callers map `to_body()` onto the HTTP error shape."""

from app.domain.states import TaskState


class DomainError(Exception):
    """A refused workflow operation. The database is left unchanged."""

    code = "domain_error"

    def __init__(self, message: str, *, task_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.task_id = task_id

    def to_body(self) -> dict[str, dict[str, str | None]]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "task_id": self.task_id,
            }
        }


class InvalidTransition(DomainError):
    """The requested edge is not legal, or a guard on that edge failed."""

    code = "invalid_transition"

    def __init__(
        self,
        message: str,
        *,
        task_id: str | None = None,
        from_state: TaskState | None = None,
        to_state: TaskState | None = None,
    ) -> None:
        super().__init__(message, task_id=task_id)
        self.from_state = from_state
        self.to_state = to_state


class TaskNotFound(DomainError):
    code = "task_not_found"

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task {task_id} was not found.", task_id=task_id)


class ApprovalRequired(DomainError):
    """Delivery was requested without a stored human approval for this task."""

    code = "approval_required"

    def __init__(
        self,
        message: str = "A pull request requires a stored human approval.",
        *,
        task_id: str | None = None,
    ) -> None:
        super().__init__(message, task_id=task_id)


class NotAddressed(DomainError):
    code = "not_addressed"

    def __init__(
        self,
        message: str = "The message was not addressed to the agent.",
        *,
        task_id: str | None = None,
    ) -> None:
        super().__init__(message, task_id=task_id)


class PersistenceError(DomainError):
    """The transaction could not be committed. The previous state is still in place."""

    code = "persistence_error"
