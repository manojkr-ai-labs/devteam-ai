"""Store one unified diff, or fail the task when that diff is not safe.

``invalid_diff`` means the diff is empty, has no file header, lacks a summary,
or is longer than 400 lines. ``unsafe_diff`` means a path is absolute, contains
``..``, or leaves the checkout. The diff text is stored as it was given.
"""

from app.domain.models import Actor, EvidenceDraft, FindingDraft, PatchDraft, Task
from app.domain.states import ActorType, TaskState
from app.integrations.repository import FileRead, LocalRepository
from app.persistence.repository import StateMachine

DIFF_LINE_LIMIT = 400


class PatchService:
    """Persist a caller-supplied diff, or move the task to FAILED."""

    def __init__(
        self,
        machine: StateMachine,
        repository: LocalRepository,
        *,
        agent_id: str,
        agent_name: str,
    ) -> None:
        if agent_id.strip() == "" or agent_name.strip() == "":
            raise ValueError("agent_id and agent_name are required.")
        self._machine = machine
        self._repository = repository
        self._agent = Actor(type=ActorType.AGENT, id=agent_id, name=agent_name)
        self._system = Actor(type=ActorType.SYSTEM, id="system", name="system")

    def ground(self, finding: FindingDraft) -> tuple[FindingDraft | None, tuple[str, ...]]:
        """Keep citations whose path was read, and store that read's quote."""
        quotes = {item.path: item for item in self._repository.reads}
        kept: list[EvidenceDraft] = []
        dropped: list[str] = []
        for item in finding.evidence:
            quote = quotes.get(item.path.strip().replace("\\", "/"))
            if quote is None:
                dropped.append(item.path)
                continue
            kept.append(
                EvidenceDraft(
                    path=quote.path,
                    start_line=quote.start_line,
                    end_line=quote.end_line,
                    excerpt=quote.excerpt,
                    reason=item.reason,
                )
            )
        if not kept:
            return None, tuple(dropped)
        return (
            FindingDraft(
                hypothesis=finding.hypothesis,
                summary=finding.summary,
                recommended_action=finding.recommended_action,
                uncertainties=_with_drops(finding.uncertainties, dropped),
                evidence=kept,
            ),
            tuple(dropped),
        )

    def store(
        self,
        task: Task,
        *,
        diff: str,
        summary: str,
        affected_files: list[str],
        test_recommendations: list[str],
        finding: FindingDraft,
    ) -> Task:
        """Store `diff` on an INVESTIGATING task, or fail closed."""
        code = self._rejection(diff, affected_files, summary)
        if code is not None:
            return self._machine.fail(task.id, stage="patch", error=code, actor=self._system)
        current = self._machine.get_task(task.id)
        if current.state != TaskState.INVESTIGATING:
            return current
        grounded, _dropped = self.ground(finding)
        if grounded is None:
            return current
        paths = _unified_paths(diff)
        declared = [item.strip().replace("\\", "/") for item in affected_files]
        recommendations = [item.strip() for item in test_recommendations if item.strip()]
        draft = PatchDraft(
            diff=diff,
            summary=summary.strip(),
            affected_files=_unique([*declared, *paths]),
            test_recommendations=recommendations,
        )
        return self._machine.transition(
            task.id,
            TaskState.PATCH_PROPOSED,
            self._agent,
            finding=grounded,
            patch=draft,
        )

    def files_for(self, finding: FindingDraft) -> list[FileRead]:
        """Return the stored reads for the finding's cited paths."""
        quotes = {item.path: item for item in self._repository.reads}
        files: list[FileRead] = []
        for item in finding.evidence:
            quote = quotes.get(item.path)
            if quote is not None and quote not in files:
                files.append(quote)
        return files

    def _rejection(self, diff: str, affected_files: list[str], summary: str) -> str | None:
        if diff.strip() == "" or summary.strip() == "":
            return "invalid_diff"
        if len(diff.splitlines()) > DIFF_LINE_LIMIT:
            return "invalid_diff"
        paths = _unified_paths(diff)
        if not paths:
            return "invalid_diff"
        declared = [item.strip().replace("\\", "/") for item in affected_files]
        if any(item == "" for item in declared):
            return "invalid_diff"
        for path in [*paths, *declared]:
            if not self._repository.contains(path):
                return "unsafe_diff"
        return None


def _with_drops(uncertainties: str, dropped: list[str]) -> str:
    if not dropped:
        return uncertainties
    note = "Dropped citations that were not read: " + ", ".join(dropped)
    if uncertainties.strip() == "":
        return note
    return f"{uncertainties.rstrip()}\n{note}"


def _unified_paths(diff: str) -> list[str]:
    found: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            tokens = line.split()
            if len(tokens) >= 4:
                for token, prefix in ((tokens[2], "a"), (tokens[3], "b")):
                    path = _git_path(token, prefix)
                    if path is not None:
                        found.append(path)
            continue
        if line.startswith("--- "):
            path = _git_path(line[4:].split("\t", 1)[0].strip(), "a")
        elif line.startswith("+++ "):
            path = _git_path(line[4:].split("\t", 1)[0].strip(), "b")
        else:
            path = None
        if path is not None:
            found.append(path)
    return _unique(found)


def _git_path(token: str, prefix: str) -> str | None:
    if token == "/dev/null":
        return None
    marker = prefix + "/"
    if token.startswith(marker):
        return token[len(marker) :]
    return token


def _unique(items: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
