"""Ports for later phases. Protocols only: no socket, model, Docker, or dossier."""

from collections.abc import Sequence
from typing import Protocol

from app.domain.models import PullRequestSpec


class Switch(Protocol):
    """Room messaging. The listener owns the socket; this is the call surface."""

    def post_message(self, room_id: str, text: str) -> str:
        """Post text to a room and return the new message id."""
        ...

    def read_context(self, room_id: str) -> Sequence[str]:
        """Return recent room messages, oldest first."""
        ...

    def connect_to_room(
        self,
        room_id: str,
        *,
        connection_id: str,
        start_from: str | None = None,
    ) -> str:
        """Open or resume a room connection and return its connection id."""
        ...

    def list_participants(self, room_id: str) -> Sequence[str]:
        """Return participant ids currently in the room."""
        ...


class Repository(Protocol):
    """A checked-out tree. This is not the task database."""

    def checkout(self, repository: str, ref: str) -> str:
        """Materialize `ref` and return the working-tree path."""
        ...

    def read_file(self, repository: str, ref: str, path: str) -> str:
        """Return file text at `ref`."""
        ...


class Sandbox(Protocol):
    """Run a command outside the agent process."""

    def run(self, command: str, *, cwd: str) -> tuple[int, str, str]:
        """Return exit code, stdout, and stderr."""
        ...


class GitHubRead(Protocol):
    """Read-only GitHub access."""

    def resolve_ref(self, repository: str, ref: str) -> str:
        """Return the commit SHA that `ref` currently names."""
        ...

    def read_file(self, repository: str, ref: str, path: str) -> str:
        """Return file text from the remote repository at `ref`."""
        ...


class GitHubWrite(Protocol):
    """GitHub writes. Approval delivery uses this in a later phase."""

    def create_pull_request(
        self,
        repository: str,
        *,
        title: str,
        body: str,
        head_branch: str,
        base_ref: str,
    ) -> PullRequestSpec:
        """Open a pull request and return its URL and number."""
        ...


class Reasoning(Protocol):
    """Model completion. No model is bound in this phase."""

    def complete(self, instructions: str, user_text: str) -> str:
        """Return model text for the instruction and user text."""
        ...
