"""Read-only local checkout.

``resolve``, ``search``, ``read``, and ``tree`` never fetch GitHub and never
start a container. A drive letter, a leading slash, or a ``..`` segment is
rejected before the filesystem is touched. Every successful ``read`` stores
the file text that was actually read.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from app.domain.paths import is_repo_relative_path

_SKIP_DIRS = frozenset({".git", ".venv", "__pycache__", "stitch_devteamai"})


@dataclass(frozen=True)
class FileRead:
    """One file that was read. ``excerpt`` is the file text."""

    path: str
    start_line: int
    end_line: int
    excerpt: str


class LocalRepository:
    """The demo checkout. Callers pass repository-relative paths only."""

    def __init__(self, checkout: Path) -> None:
        root = checkout.resolve()
        if not root.is_dir():
            raise ValueError("checkout must be a local directory.")
        self._root = root
        self.reads: list[FileRead] = []
        self.rejected: list[str] = []
        self.misses: list[str] = []

    def resolve(self, repository: str | None, git_ref: str) -> bool:
        """Return whether `repository` selects this checkout.

        ``.`` and the checkout directory name resolve. Absolute paths, ``..``,
        and GitHub URLs do not. Nothing is cloned.
        """
        if not isinstance(repository, str) or git_ref.strip() == "":
            return False
        if not self._root.is_dir():
            return False
        reference = repository.strip()
        if reference == ".":
            return True
        if not is_repo_relative_path(reference):
            return False
        return reference.replace("\\", "/") == self._root.name

    def search(self, query: str) -> list[str]:
        """Return relative paths whose path or text contains `query`."""
        needle = query.strip()
        if needle == "":
            return []
        matches: list[str] = []
        for relative in self.tree():
            if needle in relative:
                matches.append(relative)
                continue
            text = self._scan(relative)
            if text is not None and needle in text:
                matches.append(relative)
        return matches

    def read(self, path: str) -> FileRead | None:
        """Read one relative file and store its text.

        Unsafe paths are recorded in ``rejected`` and are not opened. A missing
        file is recorded in ``misses``. A second read of the same file returns
        the stored quote.
        """
        normalized = path.strip().replace("\\", "/")
        if not is_repo_relative_path(normalized):
            self._remember(self.rejected, path)
            return None
        try:
            resolved = self._root.joinpath(*normalized.split("/")).resolve()
            relative = resolved.relative_to(self._root).as_posix()
        except (OSError, ValueError):
            self._remember(self.rejected, path)
            return None
        if not is_repo_relative_path(relative):
            self._remember(self.rejected, path)
            return None
        existing = self._stored(relative)
        if existing is not None:
            return existing
        if not resolved.is_file():
            self._remember(self.misses, relative)
            return None
        try:
            text = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            self._remember(self.misses, relative)
            return None
        if text == "":
            self._remember(self.misses, relative)
            return None
        end_line = len(text.splitlines())
        record = FileRead(
            path=relative,
            start_line=1,
            end_line=end_line if end_line >= 1 else 1,
            excerpt=text,
        )
        self.reads.append(record)
        return record

    def tree(self) -> list[str]:
        """List repository-relative files. Skipped directories are not walked."""
        found: list[str] = []
        for directory, dirnames, filenames in os.walk(self._root):
            dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS]
            for name in filenames:
                candidate = Path(directory) / name
                try:
                    resolved = candidate.resolve()
                    relative = resolved.relative_to(self._root).as_posix()
                except (OSError, ValueError):
                    continue
                if is_repo_relative_path(relative):
                    found.append(relative)
        return sorted(found)

    def contains(self, path: str) -> bool:
        """Return whether `path` stays inside this checkout. Does not read it."""
        relative = path.strip().replace("\\", "/")
        if not is_repo_relative_path(relative):
            return False
        try:
            resolved = self._root.joinpath(*relative.split("/")).resolve()
            resolved.relative_to(self._root)
        except (OSError, ValueError):
            return False
        return True

    def _scan(self, relative: str) -> str | None:
        try:
            return self._root.joinpath(*relative.split("/")).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def _stored(self, relative: str) -> FileRead | None:
        for item in self.reads:
            if item.path == relative:
                return item
        return None

    def _remember(self, bucket: list[str], value: str) -> None:
        if value not in bucket:
            bucket.append(value)
