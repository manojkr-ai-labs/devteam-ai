"""Repository-relative path checks shared by evidence and later patch rules."""


def is_repo_relative_path(path: str) -> bool:
    """Return whether `path` stays inside a checkout.

    Absolute paths, drive letters, and any `..` segment are rejected. The check
    is lexical. It does not look at the filesystem.
    """
    if path.strip() == "" or "\x00" in path or ":" in path:
        return False
    if path.startswith(("/", "\\")):
        return False
    parts = path.replace("\\", "/").split("/")
    return all(part not in {"", ".."} for part in parts)
