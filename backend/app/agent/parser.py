"""Turn an addressed room message into an issue or a decision command.

`approve`, `reject`, and `cancel` count only when that ASCII word is the first
token after the `@devteam` mention. The comparison is case-insensitive. A
mid-sentence "approve", or a non-ASCII lookalike, stays an issue.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

LOG_BYTE_LIMIT = 64 * 1024
_MENTION = re.compile(r"@devteam(?![A-Za-z0-9_])", re.IGNORECASE)
_GITHUB_URL = re.compile(
    r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?(?:/[^\s]*)?",
    re.IGNORECASE,
)
_COMMAND_WORDS = frozenset({"approve", "reject", "cancel"})


class ParseKind(StrEnum):
    NOT_ADDRESSED = "not_addressed"
    EMPTY = "empty"
    COMMAND = "command"
    ISSUE = "issue"


class CommandName(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"


@dataclass(frozen=True)
class ParsedCommand:
    """A decision command. `task_id` is set only when the token is a UUID."""

    name: CommandName
    task_id: str | None
    task_token: str | None
    reason: str | None


@dataclass(frozen=True)
class ParsedIssue:
    """Issue fields taken from the message. `git_ref` defaults to `main`."""

    repository: str | None
    git_ref: str
    ref_explicit: bool
    title: str
    description: str
    logs: str | None
    logs_truncated: bool


@dataclass(frozen=True)
class ParsedMessage:
    kind: ParseKind
    command: ParsedCommand | None = None
    issue: ParsedIssue | None = None


def parse_message(text: str) -> ParsedMessage:
    """Parse one room body. Unaddressed text creates neither an issue nor a command."""
    match = _MENTION.search(text)
    if match is None:
        return ParsedMessage(kind=ParseKind.NOT_ADDRESSED)
    remainder = text[match.end() :]
    tokens = remainder.split()
    if not tokens:
        return ParsedMessage(kind=ParseKind.EMPTY)
    command_name = _command_name(tokens[0])
    if command_name is not None:
        return ParsedMessage(kind=ParseKind.COMMAND, command=_parse_command(remainder, command_name))
    issue = _parse_issue(remainder)
    if issue.description == "" and issue.repository is None and issue.logs is None:
        return ParsedMessage(kind=ParseKind.EMPTY)
    return ParsedMessage(kind=ParseKind.ISSUE, issue=issue)


def _command_name(token: str) -> CommandName | None:
    if not token.isascii() or not token.isalpha():
        return None
    lowered = token.lower()
    if lowered not in _COMMAND_WORDS:
        return None
    return CommandName(lowered)


def _parse_command(remainder: str, name: CommandName) -> ParsedCommand:
    parts = remainder.split(maxsplit=2)
    task_token = parts[1] if len(parts) > 1 else None
    reason = parts[2].strip() if len(parts) > 2 else ""
    return ParsedCommand(
        name=name,
        task_id=None if task_token is None else _canonical_uuid(task_token),
        task_token=task_token,
        reason=reason or None,
    )


def _canonical_uuid(token: str) -> str | None:
    try:
        return str(UUID(token))
    except ValueError:
        return None


def _parse_issue(body: str) -> ParsedIssue:
    repository: str | None = None
    git_ref = "main"
    ref_explicit = False
    dropped_investigate = False
    header = True
    content: list[str] = []

    for line in body.splitlines():
        stripped = line.strip()
        if header:
            if stripped == "":
                continue
            if _is_investigate(stripped) and not dropped_investigate and repository is None:
                dropped_investigate = True
                continue
            labeled_repo = _label_value(stripped, "repo")
            if labeled_repo is not None and repository is None:
                repository = labeled_repo or None
                continue
            labeled_ref = _label_value(stripped, "ref")
            if labeled_ref is not None and not ref_explicit:
                ref_explicit = True
                git_ref = labeled_ref or "main"
                continue
            sole_url = _sole_github_url(stripped)
            if sole_url is not None and repository is None:
                repository = sole_url
                continue
            leading_url, rest = _split_leading_github_url(stripped)
            if leading_url is not None and repository is None:
                repository = leading_url
                header = False
                if rest:
                    content.append(rest)
                continue
            header = False
        content.append(line)

    description, logs = _split_description(content)
    logs, truncated = _truncate_logs(logs)
    title = description.splitlines()[0].strip() if description else ""
    return ParsedIssue(
        repository=repository,
        git_ref=git_ref,
        ref_explicit=ref_explicit,
        title=title,
        description=description,
        logs=logs,
        logs_truncated=truncated,
    )


def _is_investigate(stripped: str) -> bool:
    return stripped.isascii() and stripped.lower() == "investigate"


def _label_value(stripped: str, label: str) -> str | None:
    prefix = f"{label}:"
    head = stripped[: len(prefix)]
    if not head.isascii() or head.lower() != prefix:
        return None
    return stripped[len(prefix) :].strip()


def _sole_github_url(stripped: str) -> str | None:
    match = _GITHUB_URL.fullmatch(stripped)
    if match is None:
        return None
    return match.group(0)


def _split_leading_github_url(stripped: str) -> tuple[str | None, str]:
    match = _GITHUB_URL.match(stripped)
    if match is None:
        return None, stripped
    rest = stripped[match.end() :].strip()
    if rest == "":
        return match.group(0), ""
    if stripped[match.end() : match.end() + 1].strip() == "" or match.end() == len(stripped):
        return match.group(0), rest
    return None, stripped


def _split_description(lines: list[str]) -> tuple[str, str | None]:
    text = "\n".join(lines).strip()
    if text == "":
        return "", None
    parts = re.split(r"\n[ \t]*\n", text, maxsplit=1)
    description = parts[0].strip()
    if len(parts) == 1:
        return description, None
    logs = parts[1].strip()
    return description, logs or None


def _truncate_logs(logs: str | None) -> tuple[str | None, bool]:
    if logs is None:
        return None, False
    raw = logs.encode("utf-8")
    if len(raw) <= LOG_BYTE_LIMIT:
        return logs, False
    clipped = raw[:LOG_BYTE_LIMIT]
    while clipped:
        try:
            return clipped.decode("utf-8"), True
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return "", True
