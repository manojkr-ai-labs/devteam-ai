"""Demo slice: intake, local investigation, and one safe diff.

The listener is constructed with the investigation stage. Tests call
``room_text_for`` and never start the socket.
"""

from collections.abc import Sequence
from pathlib import Path

from app.agent.listener import RoomListener
from app.domain.models import EvidenceDraft, FindingDraft, PatchDraft
from app.domain.states import TaskState
from app.integrations.repository import FileRead, LocalRepository
from app.integrations.switch_client import SwitchClient
from app.persistence.repository import StateMachine
from app.services.intake import IntakeService
from app.services.investigation import FILE_CAP, InvestigationService, room_text_for
from app.services.patch import DIFF_LINE_LIMIT
from tests.conftest import AGENT_ID
from tests.fakes import FakeTransport

ROOM_ID = "room-1"
CONNECTION_ID = "11111111-1111-4111-8111-111111111111"
SENDER_ID = "human-1"
SENDER_NAME = "Avery"

BILLING = "def charge(amount: int) -> int:\n    return amount\n"
ROUTES = 'ROUTE = "/billing/charge"\n'
CALLER = "from app.billing import charge\n\n\ndef test_charge() -> None:\n    assert charge(2) == 2\n"
VALID_DIFF = """diff --git a/app/billing.py b/app/billing.py
--- a/app/billing.py
+++ b/app/billing.py
@@ -1,2 +1,2 @@
 def charge(amount: int) -> int:
-    return amount
+    return amount + 1
"""


class _RecordingReasoning:
    """Stands in for a model. The service calls it only when a key is set."""

    def __init__(self, patch: PatchDraft | None = None) -> None:
        self.patch = patch
        self.issues: list[str] = []
        self.excerpts: list[Sequence[FileRead]] = []
        self.files: list[Sequence[FileRead]] = []
        self.hypotheses = 0
        self.patches = 0

    def hypothesize(self, *, issue: str, excerpts: Sequence[FileRead]) -> FindingDraft:
        self.hypotheses += 1
        self.issues.append(issue)
        self.excerpts.append(excerpts)
        return FindingDraft(
            hypothesis="charge returns its input.",
            summary="charge returns its input.",
            recommended_action="Add one to the amount.",
            evidence=[
                EvidenceDraft(
                    path="app/billing.py",
                    start_line=1,
                    end_line=1,
                    excerpt="NOT THE FILE",
                    reason="frame",
                ),
                EvidenceDraft(
                    path="nope.py",
                    start_line=1,
                    end_line=1,
                    excerpt="missing",
                    reason="guess",
                ),
            ],
        )

    def propose_patch(
        self,
        *,
        hypothesis: FindingDraft,
        files: Sequence[FileRead],
    ) -> PatchDraft:
        self.patches += 1
        self.files.append(files)
        if self.patch is None:
            raise AssertionError("propose_patch")
        return self.patch


def test_addressed_issue_returns_stored_excerpts_without_calling_a_model(
    machine: StateMachine,
    tmp_path: Path,
) -> None:
    """No reasoning key: intake then investigation, and the quote is the file."""
    checkout = _checkout(tmp_path)
    reasoning = _RecordingReasoning()
    repository, service, listener, transport = _wire(
        machine,
        checkout,
        reasoning=reasoning,
        reasoning_api_key="",
    )
    text = room_text_for(
        listener,
        message_id="m-issue",
        text=_issue(),
        sender_id=SENDER_ID,
        sender_name=SENDER_NAME,
    )
    task = machine.get_active_task(ROOM_ID)
    assert task is not None
    billing = (checkout / "app/billing.py").read_text(encoding="utf-8")
    routes = (checkout / "app/routes.py").read_text(encoding="utf-8")
    caller = (checkout / "tests/test_billing.py").read_text(encoding="utf-8")
    assert text.startswith(f"Task {task.id} is RECEIVED.")
    assert f"Task {task.id} is INVESTIGATING." in text
    assert billing in text
    assert routes in text
    assert caller in text
    assert "C:/Windows" not in text
    assert "../outside.py" not in text
    assert task.state == TaskState.INVESTIGATING
    assert task.classification == "bug"
    assert task.priority == "medium"
    assert task.summary == "charge returns the amount unchanged"
    assert [item.path for item in repository.reads] == [
        "app/billing.py",
        "app/routes.py",
        "tests/test_billing.py",
    ]
    assert [item.excerpt for item in repository.reads] == [billing, routes, caller]
    assert repository.rejected == ["C:/Windows/system.ini", "../outside.py"]
    assert "app/missing.py" in repository.misses
    assert "notes.txt" not in [item.path for item in repository.reads]
    assert len(repository.reads) <= FILE_CAP
    event = next(
        item
        for item in machine.list_events(task.id)
        if item.to_state == TaskState.INVESTIGATING
    )
    stored = event.payload["excerpts"]
    assert isinstance(stored, list)
    assert stored == [
        {
            "path": item.path,
            "start_line": item.start_line,
            "end_line": item.end_line,
            "excerpt": item.excerpt,
        }
        for item in repository.reads
    ]
    assert machine.get_patch(task.id) is None
    assert machine.get_finding(task.id) is None
    assert reasoning.hypotheses == 0
    assert reasoning.patches == 0
    assert service.patch is not None
    assert transport.connect_count == 0
    assert transport.connections == []
    assert transport.posted == []


def test_investigation_reads_at_most_eight_files(
    machine: StateMachine,
    tmp_path: Path,
) -> None:
    """Frames are read first. Search hits stop at eight files."""
    checkout = tmp_path / "wide"
    _write(checkout, "app/billing.py", BILLING)
    for number in range(10):
        _write(checkout, f"extra/f{number:02d}.py", "charge\n")
    repository, _service, listener, transport = _wire(
        machine,
        checkout,
        reasoning_api_key="",
    )
    room_text_for(
        listener,
        message_id="m-wide",
        text=_frame_issue(),
        sender_id=SENDER_ID,
        sender_name=SENDER_NAME,
    )
    paths = [item.path for item in repository.reads]
    assert paths[0] == "app/billing.py"
    assert len(paths) == FILE_CAP
    assert "extra/f06.py" in paths
    assert "extra/f07.py" not in paths
    assert "extra/f09.py" not in paths
    for item in repository.reads:
        assert item.excerpt == (checkout / item.path).read_text(encoding="utf-8")
    assert transport.connect_count == 0


def test_absolute_and_github_references_do_not_resolve(
    machine: StateMachine,
    tmp_path: Path,
) -> None:
    """A local checkout is the only source. Absolute paths and GitHub URLs stay RECEIVED."""
    checkout = _checkout(tmp_path)
    repository = LocalRepository(checkout)
    intake = IntakeService(machine, agent_id=AGENT_ID)
    transport = FakeTransport()
    cases = (
        ("room-abs", "m-abs", "C:/Windows"),
        ("room-gh", "m-gh", "https://github.com/acme/widgets"),
    )
    for room_id, message_id, reference in cases:
        service = InvestigationService(
            machine,
            repository,
            agent_id=AGENT_ID,
            reasoning_api_key="",
        )
        listener = _listener(intake, service, room_id, transport)
        text = room_text_for(
            listener,
            message_id=message_id,
            text=_repo_issue(reference),
            sender_id=SENDER_ID,
            sender_name=SENDER_NAME,
        )
        task = machine.get_active_task(room_id)
        assert task is not None
        assert task.state == TaskState.RECEIVED
        assert task.classification is None
        assert "did not resolve" in text
        assert machine.get_patch(task.id) is None
    assert repository.reads == []
    assert transport.connect_count == 0
    assert transport.posted == []


def test_foreign_citation_is_dropped_and_no_diff_is_invented(
    machine: StateMachine,
    tmp_path: Path,
) -> None:
    """A key with only an unread citation stays INVESTIGATING and does not propose."""
    checkout = _checkout(tmp_path)
    reasoning = _RecordingReasoning(patch=None)
    _repository, _service, listener, transport = _wire(
        machine,
        checkout,
        room_id="room-drop",
        reasoning=reasoning,
        reasoning_api_key="test-key",
    )

    def hypothesize(self: _RecordingReasoning, *, issue: str, excerpts: Sequence[FileRead]) -> FindingDraft:
        self.hypotheses += 1
        self.issues.append(issue)
        self.excerpts.append(excerpts)
        return FindingDraft(
            hypothesis="Somewhere else.",
            summary="Somewhere else.",
            recommended_action="Look again.",
            evidence=[
                EvidenceDraft(
                    path="nope.py",
                    start_line=1,
                    end_line=1,
                    excerpt="missing",
                    reason="guess",
                )
            ],
        )

    reasoning.hypothesize = hypothesize.__get__(reasoning, _RecordingReasoning)
    text = room_text_for(
        listener,
        message_id="m-drop",
        text=_issue(),
        sender_id=SENDER_ID,
        sender_name=SENDER_NAME,
    )
    task = machine.get_active_task("room-drop")
    assert task is not None
    assert task.state == TaskState.INVESTIGATING
    assert "Dropped citations that were not read: nope.py" in text
    assert (checkout / "app/billing.py").read_text(encoding="utf-8") in text
    assert "nope.py" not in text.split("Dropped citations")[0]
    assert machine.get_patch(task.id) is None
    assert reasoning.hypotheses == 1
    assert reasoning.patches == 0
    assert "amount + 1" not in reasoning.issues[0]
    assert transport.connect_count == 0


def test_grounded_model_patch_stores_the_quote_and_the_given_diff(
    machine: StateMachine,
    tmp_path: Path,
) -> None:
    """The stored excerpt is the file that was read. The diff is the one returned."""
    checkout = _checkout(tmp_path)
    reasoning = _RecordingReasoning(
        patch=PatchDraft(
            diff=VALID_DIFF,
            summary="Add one to the amount.",
            affected_files=["app/billing.py"],
            test_recommendations=["pytest tests/test_billing.py"],
        )
    )
    repository, _service, listener, transport = _wire(
        machine,
        checkout,
        room_id="room-model",
        reasoning=reasoning,
        reasoning_api_key="test-key",
    )
    text = room_text_for(
        listener,
        message_id="m-model",
        text=_issue(),
        sender_id=SENDER_ID,
        sender_name=SENDER_NAME,
    )
    task = machine.get_active_task("room-model")
    assert task is not None
    billing = (checkout / "app/billing.py").read_text(encoding="utf-8")
    assert task.state == TaskState.PATCH_PROPOSED
    assert f"Task {task.id} is PATCH_PROPOSED." in text
    finding = machine.get_finding(task.id)
    assert finding is not None
    assert len(finding.evidence) == 1
    assert finding.evidence[0].path == "app/billing.py"
    assert finding.evidence[0].excerpt == billing
    assert finding.evidence[0].excerpt != "NOT THE FILE"
    assert "nope.py" in finding.uncertainties
    patch = machine.get_patch(task.id)
    assert patch is not None
    assert patch.diff == VALID_DIFF
    assert patch.affected_files == ["app/billing.py"]
    assert patch.test_recommendations == ["pytest tests/test_billing.py"]
    assert reasoning.hypotheses == 1
    assert reasoning.patches == 1
    assert [item.path for item in reasoning.files[0]] == ["app/billing.py"]
    assert reasoning.files[0][0].excerpt == billing
    assert "amount + 1" not in reasoning.issues[0]
    assert {item.path for item in reasoning.excerpts[0]} == {item.path for item in repository.reads}
    assert "notes.txt" not in {item.path for item in reasoning.excerpts[0]}
    assert transport.connect_count == 0


def test_patch_refuses_unsafe_and_invalid_diffs(
    machine: StateMachine,
    tmp_path: Path,
) -> None:
    """Traversal, absolute, empty, headerless, and oversize diffs fail before apply."""
    checkout = _checkout(tmp_path)
    repository, service, listener, transport = _wire(
        machine,
        checkout,
        room_id="room-fail",
        reasoning_api_key="",
    )
    oversize = "\n".join(
        [
            "diff --git a/app/billing.py b/app/billing.py",
            "--- a/app/billing.py",
            "+++ b/app/billing.py",
            *(["+x"] * (DIFF_LINE_LIMIT - 2)),
        ]
    )
    traversal = "\n".join(
        [
            "diff --git a/../secret.py b/../secret.py",
            "--- a/../secret.py",
            "+++ b/../secret.py",
            "@@ -1 +1 @@",
            "-a",
            "+b",
        ]
    )
    absolute = "\n".join(
        [
            "--- /etc/passwd",
            "+++ /etc/passwd",
            "@@ -1 +1 @@",
            "-root",
            "+root",
        ]
    )
    cases = (
        ("m-empty", "", "invalid_diff"),
        ("m-text", "this is not a diff\n", "invalid_diff"),
        ("m-long", oversize, "invalid_diff"),
        ("m-dotdot", traversal, "unsafe_diff"),
        ("m-abs", absolute, "unsafe_diff"),
    )
    for message_id, diff, code in cases:
        room_text_for(
            listener,
            message_id=message_id,
            text=_issue(),
            sender_id=SENDER_ID,
            sender_name=SENDER_NAME,
        )
        task = machine.get_active_task("room-fail")
        assert task is not None
        assert task.state == TaskState.INVESTIGATING
        failed = service.patch.store(
            task,
            diff=diff,
            summary="Change charge.",
            affected_files=["app/billing.py"],
            test_recommendations=[],
            finding=_finding(),
        )
        assert failed.state == TaskState.FAILED
        assert machine.get_patch(task.id) is None
        event = machine.list_events(task.id)[-1]
        assert event.to_state == TaskState.FAILED
        assert event.payload["stage"] == "patch"
        assert event.payload["error"] == code
    assert len(oversize.splitlines()) > DIFF_LINE_LIMIT
    assert transport.connect_count == 0


def test_patch_stores_one_unified_diff_from_the_caller(
    machine: StateMachine,
    tmp_path: Path,
) -> None:
    """A diff supplied to the patch service is stored, with the read quote."""
    checkout = _checkout(tmp_path)
    repository, service, listener, transport = _wire(
        machine,
        checkout,
        room_id="room-store",
        reasoning_api_key="",
    )
    room_text_for(
        listener,
        message_id="m-store",
        text=_issue(),
        sender_id=SENDER_ID,
        sender_name=SENDER_NAME,
    )
    task = machine.get_active_task("room-store")
    assert task is not None
    billing = next(item for item in repository.reads if item.path == "app/billing.py")
    stored = service.patch.store(
        task,
        diff=VALID_DIFF,
        summary="Add one to the amount.",
        affected_files=["app/billing.py"],
        test_recommendations=["pytest tests/test_billing.py"],
        finding=FindingDraft(
            hypothesis="charge returns its input.",
            summary="charge returns its input.",
            recommended_action="Add one to the amount.",
            evidence=[
                EvidenceDraft(
                    path="app/billing.py",
                    start_line=9,
                    end_line=9,
                    excerpt="not the quote",
                    reason="frame",
                ),
                EvidenceDraft(
                    path="nope.py",
                    start_line=1,
                    end_line=1,
                    excerpt="missing",
                    reason="guess",
                ),
            ],
        ),
    )
    assert stored.state == TaskState.PATCH_PROPOSED
    finding = machine.get_finding(task.id)
    assert finding is not None
    assert len(finding.evidence) == 1
    assert finding.evidence[0].excerpt == billing.excerpt
    assert finding.evidence[0].excerpt == (checkout / "app/billing.py").read_text(encoding="utf-8")
    assert "nope.py" in finding.uncertainties
    patch = machine.get_patch(task.id)
    assert patch is not None
    assert patch.diff == VALID_DIFF
    assert len(patch.diff.splitlines()) <= DIFF_LINE_LIMIT
    assert patch.summary == "Add one to the amount."
    assert patch.affected_files == ["app/billing.py"]
    assert patch.test_recommendations == ["pytest tests/test_billing.py"]
    assert transport.connect_count == 0


def _wire(
    machine: StateMachine,
    checkout: Path,
    *,
    room_id: str = ROOM_ID,
    reasoning: _RecordingReasoning | None = None,
    reasoning_api_key: str | None = None,
) -> tuple[LocalRepository, InvestigationService, RoomListener, FakeTransport]:
    repository = LocalRepository(checkout)
    service = InvestigationService(
        machine,
        repository,
        agent_id=AGENT_ID,
        reasoning=reasoning,
        reasoning_api_key=reasoning_api_key,
    )
    transport = FakeTransport()
    intake = IntakeService(machine, agent_id=AGENT_ID)
    listener = _listener(intake, service, room_id, transport)
    return repository, service, listener, transport


def _listener(
    intake: IntakeService,
    service: InvestigationService,
    room_id: str,
    transport: FakeTransport,
) -> RoomListener:
    client = SwitchClient(
        "https://switch.example",
        AGENT_ID,
        "test-key",
        transport=transport,
    )
    return RoomListener(
        client,
        intake,
        agent_id=AGENT_ID,
        connection_id=CONNECTION_ID,
        room_id=room_id,
        stage=service.run,
    )


def _checkout(root: Path) -> Path:
    checkout = root / "checkout"
    _write(checkout, "app/billing.py", BILLING)
    _write(checkout, "app/routes.py", ROUTES)
    _write(checkout, "tests/test_billing.py", CALLER)
    _write(checkout, "notes.txt", "unrelated\n")
    return checkout


def _write(root: Path, relative: str, text: str) -> None:
    path = root.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _issue() -> str:
    return """\
@devteam
Repo: .
Ref: main

charge returns the amount unchanged

Traceback (most recent call last):
  File "app/billing.py", line 2, in charge
    return amount
  File "app/missing.py", line 1, in charge
    nope
  File "C:/Windows/system.ini", line 1, in charge
    nope
  File "../outside.py", line 3, in charge
    nope
GET "/billing/charge" returned the raw amount.
"""


def _frame_issue() -> str:
    return """\
@devteam
Repo: .
Ref: main

too many charge hits

Traceback (most recent call last):
  File "app/billing.py", line 1, in charge
    return amount
"""


def _repo_issue(reference: str) -> str:
    return f"""\
@devteam
Repo: {reference}
Ref: main

charge returns the amount unchanged
"""


def _finding() -> FindingDraft:
    return FindingDraft(
        hypothesis="charge returns its input.",
        summary="charge returns its input.",
        recommended_action="Change the return.",
        evidence=[
            EvidenceDraft(
                path="app/billing.py",
                start_line=1,
                end_line=1,
                excerpt="x",
                reason="frame",
            )
        ],
    )
