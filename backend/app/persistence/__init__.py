"""Task persistence. StateMachine is the only writer of task.state."""

from app.persistence.repository import StateMachine

__all__ = ["StateMachine"]
