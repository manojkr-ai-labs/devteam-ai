"""State-machine tests for eval gate G0.

Cases are the ones edge-case.md assigns to this module, plus the transition
guards in architecture section 7.
"""

import logging
import sqlite3
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.errors import ApprovalRequired, InvalidTransition, PersistenceError, TaskNotFound
from app.domain.models import (
    Actor,
    EvidenceDraft,
    FindingDraft,
    PatchDraft,
    PullRequestSpec,
    Task,
    ValidationDraft,
)
from app.domain.paths import is_repo_relative_path
from app.domain.states import ALLOWED, ActorType, TaskState, actor_for, is_terminal
from app.persistence.repository import StateMachine
from tests.conftest import AGENT_ID

AGENT = Actor(type=ActorType.AGENT, id=AGENT_ID, name="devteam")
HUMAN = Actor(type=ActorType.HUMAN, id="user-reviewer", name="Reviewer")
SYSTEM = Actor(type=ActorType.SYSTEM, id="system", name="system")
ACTORS = {ActorType.AGENT: AGENT, ActorType.HUMAN: HUMAN, ActorType.SYSTEM: SYSTEM}

_HAPPY_PATH = [
    TaskState.RECEIVED,
    TaskState.TRIAGED,
    TaskState.INVESTIGATING,
    TaskState.PATCH_PROPOSED,
    TaskState.VALIDATING,
    TaskState.AWAITING_APPROVAL,
    TaskState.APPROVED,
    TaskState.PR_CREATED,
]


def received(
    machine: StateMachine,
    *,
    room: str = "room-1",
    message: str = "msg-1",
    title: str = "Checkout API returns HTTP 500",
    repository: str | None = "acme/checkout",
) -> Task:
    return machine.create_task(
        switch_room_id=room,
        origin_message_id=message,
        title=title,
        description="Checkout API returns HTTP 500 after user login.",
        logs="Traceback (most recent call last):\n  File checkout.py",
        repository=repository,
    )


def finding_draft(path: str = "checkout.py") -> FindingDraft:
    return FindingDraft(
        hypothesis="Checkout reads a session field that login never sets.",
        summary="The handler assumes session.user_id.",
        recommended_action="Set the field during login or reject a missing session.",
        evidence=[
            EvidenceDraft(
                path=path,
                start_line=40,
                end_line=44,
                excerpt="user_id = session['user_id']",
                reason="This line raises when login did not store user_id.",
            )
        ],
    )


def patch_draft() -> PatchDraft:
    return PatchDraft(
        diff="--- a/checkout.py\n+++ b/checkout.py\n@@ -1 +1 @@\n-old\n+new\n",
        summary="Set the session field the checkout handler expects.",
        affected_files=["checkout.py"],
        test_recommendations=["pytest -q tests/test_checkout.py"],
    )


def validation_draft(exit_code: int = 0) -> ValidationDraft:
    passed = exit_code == 0
    return ValidationDraft(
        command="pytest -q",
        exit_code=exit_code,
        stdout="1 passed\n" if passed else "",
        stderr="" if passed else "1 failed\n",
    )


def pull_request_for(task_id: str) -> PullRequestSpec:
    return PullRequestSpec(
        url="https://github.com/acme/checkout/pull/1",
        number=1,
        head_branch=f"devteam/{task_id}",
    )


def step(machine: StateMachine, task_id: str, nxt: TaskState) -> None:
    actor = ACTORS[actor_for(nxt)]
    if nxt is TaskState.TRIAGED:
        machine.transition(
            task_id,
            nxt,
            actor,
            classification="bug",
            priority="high",
            summary="Checkout fails after login.",
        )
    elif nxt is TaskState.PATCH_PROPOSED:
        machine.transition(task_id, nxt, actor, finding=finding_draft(), patch=patch_draft())
    elif nxt is TaskState.VALIDATING:
        machine.transition(task_id, nxt, actor, apply_check="")
    elif nxt is TaskState.AWAITING_APPROVAL:
        machine.transition(task_id, nxt, actor, validation=validation_draft())
    elif nxt is TaskState.APPROVED:
        machine.transition(task_id, nxt, actor, switch_message_id="msg-approve")
    elif nxt is TaskState.PR_CREATED:
        machine.transition(task_id, nxt, actor, pull_request=pull_request_for(task_id))
    else:
        machine.transition(task_id, nxt, actor)


def drive(machine: StateMachine, task_id: str, target: TaskState) -> None:
    current = machine.get_task(task_id).state
    start = _HAPPY_PATH.index(current)
    end = _HAPPY_PATH.index(target)
    if end < start:
        raise AssertionError(f"Cannot drive from {current.value} to {target.value}.")
    for nxt in _HAPPY_PATH[start + 1 : end + 1]:
        step(machine, task_id, nxt)


def reach_terminal(machine: StateMachine, task_id: str, terminal: TaskState) -> None:
    if terminal is TaskState.FAILED:
        machine.fail(task_id, stage="triage", error="timeout", actor=SYSTEM)
    elif terminal is TaskState.CANCELLED:
        machine.transition(
            task_id,
            TaskState.CANCELLED,
            HUMAN,
            switch_message_id="msg-cancel",
        )
    elif terminal is TaskState.REJECTED:
        drive(machine, task_id, TaskState.AWAITING_APPROVAL)
        machine.transition(
            task_id,
            TaskState.REJECTED,
            HUMAN,
            switch_message_id="msg-reject",
            reason="The patch does not fix the login session.",
        )
    elif terminal is TaskState.PR_CREATED:
        drive(machine, task_id, TaskState.PR_CREATED)
    else:
        raise AssertionError(terminal)


def test_allowed_map_matches_the_architecture() -> None:
    assert set(ALLOWED) == set(TaskState)
    assert ALLOWED[TaskState.RECEIVED] == {
        TaskState.TRIAGED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    }
    assert TaskState.CANCELLED not in ALLOWED[TaskState.APPROVED]
    assert ALLOWED[TaskState.APPROVED] == {TaskState.PR_CREATED, TaskState.FAILED}
    for state in (TaskState.PR_CREATED, TaskState.REJECTED, TaskState.FAILED, TaskState.CANCELLED):
        assert ALLOWED[state] == set()
        assert is_terminal(state)
    assert actor_for(TaskState.TRIAGED) is ActorType.AGENT
    assert actor_for(TaskState.APPROVED) is ActorType.HUMAN
    assert actor_for(TaskState.PR_CREATED) is ActorType.SYSTEM
    assert actor_for(TaskState.FAILED) is ActorType.SYSTEM


@pytest.mark.parametrize(
    ("path", "ok"),
    [
        ("checkout.py", True),
        ("src/checkout.py", True),
        ("../checkout.py", False),
        ("/etc/passwd", False),
        ("C:/Windows/system.ini", False),
        ("src/../../etc/passwd", False),
        ("", False),
    ],
)
def test_repo_relative_paths(path: str, ok: bool) -> None:
    assert is_repo_relative_path(path) is ok


def test_contracts_reject_unknown_fields(machine: StateMachine) -> None:
    task = received(machine)
    assert Task.model_validate_json(task.model_dump_json()) == task
    with pytest.raises(ValidationError):
        Task.model_validate({**task.model_dump(mode="json"), "injected": True})
    with pytest.raises(ValidationError):
        FindingDraft.model_validate(
            {**finding_draft().model_dump(), "tool_request": "open_pull_request"}
        )


def test_schema_has_domain_tables_and_foreign_keys(machine: StateMachine) -> None:
    again = StateMachine(machine.database_path, agent_id=AGENT_ID)
    task = received(machine)
    assert again.get_task(task.id).id == task.id
    conn = sqlite3.connect(machine.database_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        names = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "task",
            "workflow_event",
            "finding",
            "finding_evidence",
            "patch",
            "validation_run",
            "approval",
            "pull_request",
        } <= names
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO workflow_event (
                    id, task_id, from_state, to_state, actor_type, actor_id, actor_name,
                    payload, created_at
                ) VALUES (?, ?, 'RECEIVED', 'TRIAGED', 'agent', 'a', 'devteam', '{}', ?)
                """,
                (str(uuid4()), str(uuid4()), "2026-01-01T00:00:00.000000Z"),
            )
    finally:
        conn.close()


def test_domain_stays_free_of_infrastructure() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "domain"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for banned in ("fastapi", "httpx", "docker", "sqlite3", "github"):
        assert banned not in source


def test_legal_path_reaches_pr_created(machine: StateMachine) -> None:
    task = received(machine)
    assert task.state is TaskState.RECEIVED
    assert machine.list_events(task.id) == []
    drive(machine, task.id, TaskState.PR_CREATED)
    stored = machine.get_task(task.id)
    events = machine.list_events(task.id)
    assert stored.state is TaskState.PR_CREATED
    assert [event.to_state for event in events] == _HAPPY_PATH[1:]
    assert [event.from_state for event in events] == _HAPPY_PATH[:-1]
    assert [event.actor_type for event in events] == [
        ActorType.AGENT,
        ActorType.AGENT,
        ActorType.AGENT,
        ActorType.AGENT,
        ActorType.AGENT,
        ActorType.HUMAN,
        ActorType.SYSTEM,
    ]
    finding = machine.get_finding(task.id)
    assert finding is not None
    assert finding.evidence[0].excerpt == "user_id = session['user_id']"
    patch = machine.get_patch(task.id)
    assert patch is not None
    assert patch.affected_files == ["checkout.py"]
    runs = machine.list_validation_runs(task.id)
    assert runs[0].status == "passed"
    assert runs[0].exit_code == 0
    assert runs[0].command == "pytest -q"
    assert runs[0].stdout == "1 passed\n"
    approval = machine.get_approval(task.id)
    assert approval is not None
    assert approval.decision == "approved"
    assert approval.reviewer_id == HUMAN.id
    pull_request = machine.get_pull_request(task.id)
    assert pull_request is not None
    assert pull_request.url == "https://github.com/acme/checkout/pull/1"
    assert pull_request.base_ref == "main"
    assert pull_request.head_branch == f"devteam/{task.id}"


def test_stage_guards_keep_incomplete_work_in_place(machine: StateMachine) -> None:
    task = received(machine)
    with pytest.raises(InvalidTransition):
        machine.transition(
            task.id,
            TaskState.TRIAGED,
            AGENT,
            classification="bug",
            priority="urgent",
            summary="Checkout fails after login.",
        )
    assert machine.get_task(task.id).classification is None
    assert machine.list_events(task.id) == []

    machine.transition(
        task.id,
        TaskState.TRIAGED,
        AGENT,
        classification="bug",
        priority="high",
        summary="Checkout fails after login.",
    )
    triaged = machine.get_task(task.id)
    assert triaged.state is TaskState.TRIAGED
    assert triaged.priority == "high"

    missing_repo = received(machine, message="msg-no-repo", repository=None)
    machine.transition(
        missing_repo.id,
        TaskState.TRIAGED,
        AGENT,
        classification="bug",
        priority="high",
        summary="Checkout fails after login.",
    )
    with pytest.raises(InvalidTransition):
        machine.transition(missing_repo.id, TaskState.INVESTIGATING, AGENT)
    assert machine.get_task(missing_repo.id).state is TaskState.TRIAGED

    drive(machine, task.id, TaskState.INVESTIGATING)
    with pytest.raises(InvalidTransition):
        machine.transition(
            task.id,
            TaskState.PATCH_PROPOSED,
            AGENT,
            finding=finding_draft("../secrets"),
            patch=patch_draft(),
        )
    assert machine.get_task(task.id).state is TaskState.INVESTIGATING
    assert machine.get_finding(task.id) is None

    drive(machine, task.id, TaskState.PATCH_PROPOSED)
    with pytest.raises(InvalidTransition):
        machine.transition(task.id, TaskState.VALIDATING, AGENT)
    assert machine.get_task(task.id).state is TaskState.PATCH_PROPOSED
    machine.transition(task.id, TaskState.VALIDATING, AGENT, apply_check="")
    apply_event = machine.list_events(task.id)[-1]
    assert apply_event.payload["apply_check"] == ""


def test_validation_status_follows_the_exit_code(machine: StateMachine) -> None:
    task = received(machine, message="msg-fail")
    drive(machine, task.id, TaskState.VALIDATING)
    updated = machine.transition(
        task.id,
        TaskState.AWAITING_APPROVAL,
        AGENT,
        payload={"status": "passed"},
        validation=validation_draft(5),
    )
    assert updated.state is TaskState.AWAITING_APPROVAL
    run = machine.list_validation_runs(task.id)[0]
    assert run.exit_code == 5
    assert run.status == "failed"
    assert run.stderr == "1 failed\n"
    event = machine.list_events(task.id)[-1]
    assert event.payload["status"] == "failed"
    assert event.payload["exit_code"] == 5


def test_rejection_requires_a_reason_and_records_one(machine: StateMachine) -> None:
    task = received(machine)
    drive(machine, task.id, TaskState.AWAITING_APPROVAL)
    with pytest.raises(InvalidTransition):
        machine.transition(task.id, TaskState.REJECTED, HUMAN, switch_message_id="msg-reject")
    assert machine.get_task(task.id).state is TaskState.AWAITING_APPROVAL
    assert machine.get_approval(task.id) is None
    rejected = machine.transition(
        task.id,
        TaskState.REJECTED,
        HUMAN,
        switch_message_id="msg-reject",
        reason="The patch does not fix the login session.",
    )
    assert rejected.state is TaskState.REJECTED
    approval = machine.get_approval(task.id)
    assert approval is not None
    assert approval.decision == "rejected"
    assert approval.reason == "The patch does not fix the login session."


def test_wrong_actor_writes_nothing(machine: StateMachine) -> None:
    task = received(machine)
    with pytest.raises(InvalidTransition) as exc_info:
        machine.transition(
            task.id,
            TaskState.TRIAGED,
            HUMAN,
            classification="bug",
            priority="high",
            summary="Checkout fails after login.",
        )
    assert exc_info.value.code == "invalid_transition"
    stored = machine.get_task(task.id)
    assert stored.state is TaskState.RECEIVED
    assert stored.classification is None
    assert machine.list_events(task.id) == []
    with pytest.raises(InvalidTransition):
        machine.fail(task.id, stage="triage", error="timeout", actor=HUMAN)
    assert machine.get_task(task.id).state is TaskState.RECEIVED


def test_failure_requires_stage_and_error(machine: StateMachine) -> None:
    task = received(machine)
    with pytest.raises(InvalidTransition):
        machine.fail(task.id, stage="  ", error="timeout", actor=SYSTEM)
    assert machine.get_task(task.id).state is TaskState.RECEIVED
    assert machine.list_events(task.id) == []


def test_pr_created_requires_a_human_approval_and_a_url(machine: StateMachine) -> None:
    task = received(machine)
    drive(machine, task.id, TaskState.APPROVED)
    with pytest.raises(InvalidTransition):
        machine.transition(task.id, TaskState.PR_CREATED, SYSTEM)
    with pytest.raises(InvalidTransition):
        machine.transition(
            task.id,
            TaskState.PR_CREATED,
            SYSTEM,
            pull_request=PullRequestSpec(
                url="https://github.com/acme/checkout/pull/9",
                number=9,
                head_branch="main",
            ),
        )
    assert machine.get_task(task.id).state is TaskState.APPROVED
    assert machine.get_pull_request(task.id) is None

    conn = sqlite3.connect(machine.database_path)
    try:
        conn.execute("DELETE FROM approval WHERE task_id = ?", (task.id,))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ApprovalRequired) as missing:
        machine.transition(
            task.id,
            TaskState.PR_CREATED,
            SYSTEM,
            pull_request=pull_request_for(task.id),
        )
    assert missing.value.code == "approval_required"
    assert missing.value.to_body()["error"]["code"] == "approval_required"
    assert machine.get_task(task.id).state is TaskState.APPROVED
    assert machine.get_pull_request(task.id) is None

    other = received(machine, message="msg-agent-approval")
    drive(machine, other.id, TaskState.APPROVED)
    conn = sqlite3.connect(machine.database_path)
    try:
        conn.execute(
            "UPDATE approval SET reviewer_id = ? WHERE task_id = ?",
            (AGENT_ID, other.id),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ApprovalRequired):
        machine.transition(
            other.id,
            TaskState.PR_CREATED,
            SYSTEM,
            pull_request=pull_request_for(other.id),
        )
    assert machine.get_task(other.id).state is TaskState.APPROVED
    assert machine.get_pull_request(other.id) is None
    assert machine.get_approval(other.id) is not None


def test_unknown_task_is_not_found(machine: StateMachine) -> None:
    missing = str(uuid4())
    with pytest.raises(TaskNotFound) as exc_info:
        machine.transition(missing, TaskState.TRIAGED, AGENT)
    body = exc_info.value.to_body()
    assert body["error"]["code"] == "task_not_found"
    assert body["error"]["task_id"] == missing


def test_active_task_excludes_terminal_states(machine: StateMachine) -> None:
    first = received(machine, message="msg-old")
    machine.fail(first.id, stage="triage", error="timeout", actor=SYSTEM)
    assert machine.get_active_task("room-1") is None
    second = received(machine, message="msg-new")
    drive(machine, second.id, TaskState.APPROVED)
    active = machine.get_active_task("room-1")
    assert active is not None
    assert active.id == second.id


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (TaskState.RECEIVED, TaskState.APPROVED),
        (TaskState.RECEIVED, TaskState.INVESTIGATING),
        (TaskState.TRIAGED, TaskState.PATCH_PROPOSED),
        (TaskState.TRIAGED, TaskState.VALIDATING),
        (TaskState.INVESTIGATING, TaskState.AWAITING_APPROVAL),
        (TaskState.PATCH_PROPOSED, TaskState.AWAITING_APPROVAL),
        (TaskState.VALIDATING, TaskState.APPROVED),
        (TaskState.APPROVED, TaskState.REJECTED),
    ],
)
def test_skips_are_rejected(machine: StateMachine, start: TaskState, target: TaskState) -> None:
    task = received(machine)
    if start is not TaskState.RECEIVED:
        drive(machine, task.id, start)
    before = machine.list_events(task.id)
    with pytest.raises(InvalidTransition) as exc_info:
        machine.transition(task.id, target, ACTORS[actor_for(target)])
    assert "Cannot move" in exc_info.value.message
    assert exc_info.value.from_state is start
    assert exc_info.value.to_state is target
    assert machine.get_task(task.id).state is start
    assert machine.list_events(task.id) == before


def test_ec_sm_01_received_to_pr_created_writes_nothing(machine: StateMachine) -> None:
    task = received(machine)
    with pytest.raises(InvalidTransition) as exc_info:
        machine.transition(
            task.id,
            TaskState.PR_CREATED,
            SYSTEM,
            pull_request=pull_request_for(task.id),
        )
    assert exc_info.value.code == "invalid_transition"
    assert exc_info.value.to_body()["error"]["task_id"] == task.id
    assert machine.get_task(task.id).state is TaskState.RECEIVED
    assert machine.list_events(task.id) == []
    assert machine.get_pull_request(task.id) is None


def test_ec_sm_02_awaiting_approval_to_pr_created_writes_nothing(machine: StateMachine) -> None:
    task = received(machine)
    drive(machine, task.id, TaskState.AWAITING_APPROVAL)
    before = machine.list_events(task.id)
    seen = set(sys.modules)
    with pytest.raises(InvalidTransition) as exc_info:
        machine.transition(
            task.id,
            TaskState.PR_CREATED,
            SYSTEM,
            pull_request=pull_request_for(task.id),
        )
    added = set(sys.modules) - seen
    assert exc_info.value.code == "invalid_transition"
    assert machine.get_task(task.id).state is TaskState.AWAITING_APPROVAL
    assert machine.list_events(task.id) == before
    assert machine.get_pull_request(task.id) is None
    assert machine.get_approval(task.id) is None
    assert not any("github" in name or name == "docker" for name in added)


def test_ec_sm_03_patch_proposed_to_approved_writes_no_approval(machine: StateMachine) -> None:
    task = received(machine)
    drive(machine, task.id, TaskState.PATCH_PROPOSED)
    before = machine.list_events(task.id)
    with pytest.raises(InvalidTransition):
        machine.transition(
            task.id,
            TaskState.APPROVED,
            HUMAN,
            switch_message_id="msg-approve",
        )
    assert machine.get_task(task.id).state is TaskState.PATCH_PROPOSED
    assert machine.list_events(task.id) == before
    assert machine.get_approval(task.id) is None


def test_ec_sm_05_approve_and_cancel_serialize(machine: StateMachine) -> None:
    task = received(machine)
    drive(machine, task.id, TaskState.AWAITING_APPROVAL)
    before = len(machine.list_events(task.id))
    barrier = threading.Barrier(2)
    outcomes: list[tuple[str, str]] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def approve() -> None:
        try:
            barrier.wait(timeout=5)
            updated = machine.transition(
                task.id,
                TaskState.APPROVED,
                HUMAN,
                switch_message_id="msg-approve",
            )
            with lock:
                outcomes.append(("ok", updated.state.value))
        except InvalidTransition:
            with lock:
                outcomes.append(("invalid_transition", TaskState.APPROVED.value))
        except Exception as exc:
            with lock:
                errors.append(exc)

    def cancel() -> None:
        try:
            barrier.wait(timeout=5)
            updated = machine.transition(
                task.id,
                TaskState.CANCELLED,
                HUMAN,
                switch_message_id="msg-cancel",
            )
            with lock:
                outcomes.append(("ok", updated.state.value))
        except InvalidTransition:
            with lock:
                outcomes.append(("invalid_transition", TaskState.CANCELLED.value))
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=approve), threading.Thread(target=cancel)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert errors == []
    final = machine.get_task(task.id)
    assert final.state in {TaskState.APPROVED, TaskState.CANCELLED}
    assert sorted(item[0] for item in outcomes) == ["invalid_transition", "ok"]
    assert len(machine.list_events(task.id)) == before + 1
    approval = machine.get_approval(task.id)
    if final.state is TaskState.APPROVED:
        assert approval is not None
        assert approval.decision == "approved"
    else:
        assert approval is None


def test_ec_sm_06_second_identical_transition_fails(machine: StateMachine) -> None:
    task = received(machine)
    machine.transition(
        task.id,
        TaskState.TRIAGED,
        AGENT,
        classification="bug",
        priority="high",
        summary="Checkout fails after login.",
    )
    with pytest.raises(InvalidTransition):
        machine.transition(
            task.id,
            TaskState.TRIAGED,
            AGENT,
            classification="bug",
            priority="high",
            summary="Checkout fails after login.",
        )
    events = machine.list_events(task.id)
    assert len(events) == 1
    assert events[0].from_state is TaskState.RECEIVED
    assert events[0].to_state is TaskState.TRIAGED
    assert machine.get_task(task.id).state is TaskState.TRIAGED


@pytest.mark.parametrize(
    "target",
    [TaskState.RECEIVED, TaskState.VALIDATING, TaskState.APPROVED],
)
def test_ec_sm_07_timeout_moves_to_failed_with_payload(
    machine: StateMachine,
    target: TaskState,
) -> None:
    task = received(machine)
    if target is not TaskState.RECEIVED:
        drive(machine, task.id, target)
    approval = machine.get_approval(task.id)
    failed = machine.fail(task.id, stage="validation", error="timeout", actor=SYSTEM)
    assert failed.state is TaskState.FAILED
    event = machine.list_events(task.id)[-1]
    assert event.from_state is target
    assert event.to_state is TaskState.FAILED
    assert event.actor_type is ActorType.SYSTEM
    assert event.payload["stage"] == "validation"
    assert event.payload["error"] == "timeout"
    if target is TaskState.APPROVED:
        assert approval is not None
        assert machine.get_approval(task.id) == approval


@pytest.mark.parametrize(
    "terminal",
    [TaskState.REJECTED, TaskState.FAILED, TaskState.CANCELLED, TaskState.PR_CREATED],
)
def test_ec_sm_08_terminal_states_have_no_outbound(
    machine: StateMachine,
    terminal: TaskState,
) -> None:
    task = received(machine)
    reach_terminal(machine, task.id, terminal)
    before = machine.list_events(task.id)
    with pytest.raises(InvalidTransition):
        machine.transition(
            task.id,
            TaskState.TRIAGED,
            AGENT,
            classification="bug",
            priority="high",
            summary="Checkout fails after login.",
        )
    assert machine.get_task(task.id).state is terminal
    assert machine.list_events(task.id) == before


def test_ec_sm_10_invalid_transition_is_a_log_line(
    machine: StateMachine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    task = received(machine)
    with caplog.at_level(logging.WARNING, logger="devteam.state_machine"):
        with pytest.raises(InvalidTransition):
            machine.transition(task.id, TaskState.PR_CREATED, SYSTEM)
    assert "invalid_transition" in caplog.text
    assert task.id in caplog.text
    assert machine.list_events(task.id) == []
    assert machine.get_task(task.id).state is TaskState.RECEIVED


def test_ec_act_04_cancel_after_approved_keeps_approval(machine: StateMachine) -> None:
    task = received(machine)
    drive(machine, task.id, TaskState.APPROVED)
    approval = machine.get_approval(task.id)
    assert approval is not None
    before = machine.list_events(task.id)
    with pytest.raises(InvalidTransition):
        machine.transition(
            task.id,
            TaskState.CANCELLED,
            HUMAN,
            switch_message_id="msg-cancel",
        )
    assert machine.get_task(task.id).state is TaskState.APPROVED
    assert machine.get_approval(task.id) == approval
    assert machine.list_events(task.id) == before


def test_ec_act_05_command_on_terminal_task_leaves_both_rows(machine: StateMachine) -> None:
    terminal = received(machine, message="msg-old", title="Old checkout failure")
    machine.fail(terminal.id, stage="triage", error="timeout", actor=SYSTEM)
    active = received(machine, message="msg-new", title="New checkout failure")
    terminal_events = machine.list_events(terminal.id)
    with pytest.raises(InvalidTransition):
        machine.transition(
            terminal.id,
            TaskState.CANCELLED,
            HUMAN,
            switch_message_id="msg-cancel",
        )
    assert machine.get_task(terminal.id).state is TaskState.FAILED
    assert machine.get_task(active.id).state is TaskState.RECEIVED
    assert machine.list_events(terminal.id) == terminal_events
    assert machine.list_events(active.id) == []


def test_ec_in_15_duplicate_origin_returns_the_existing_task(machine: StateMachine) -> None:
    first = received(machine)
    drive(machine, first.id, TaskState.TRIAGED)
    second = machine.create_task(
        switch_room_id="room-1",
        origin_message_id="msg-1",
        title="A different title",
        description="A different description.",
    )
    assert second.id == first.id
    assert second.state is TaskState.TRIAGED
    assert second.title == first.title
    assert len(machine.list_tasks()) == 1
    assert len(machine.list_events(first.id)) == 1


def test_ec_in_15_concurrent_intake_returns_one_task(machine: StateMachine) -> None:
    barrier = threading.Barrier(8)
    found: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def work() -> None:
        try:
            barrier.wait(timeout=5)
            task = machine.create_task(
                switch_room_id="room-1",
                origin_message_id="msg-race",
                title="Checkout API returns HTTP 500",
                description="Checkout API returns HTTP 500 after user login.",
            )
            with lock:
                found.append(task.id)
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert errors == []
    assert len(found) == 8
    assert len(set(found)) == 1
    assert len(machine.list_tasks()) == 1


def test_ec_db_05_locked_database_keeps_previous_state(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "locked.db"
    machine = StateMachine(str(path), agent_id=AGENT_ID, busy_timeout_ms=50, lock_attempts=2)
    task = received(machine)
    holder = sqlite3.connect(path, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    try:
        with caplog.at_level(logging.ERROR, logger="devteam.state_machine"):
            with pytest.raises(PersistenceError) as exc_info:
                machine.transition(
                    task.id,
                    TaskState.TRIAGED,
                    AGENT,
                    classification="bug",
                    priority="high",
                    summary="Checkout fails after login.",
                )
        assert exc_info.value.code == "persistence_error"
        assert exc_info.value.task_id == task.id
        assert "persistence_error" in caplog.text
    finally:
        holder.rollback()
        holder.close()
    assert machine.get_task(task.id).state is TaskState.RECEIVED
    assert machine.get_task(task.id).classification is None
    assert machine.list_events(task.id) == []


def test_ec_db_07_timestamps_are_utc(machine: StateMachine) -> None:
    before = datetime.now(UTC) - timedelta(seconds=2)
    task = received(machine)
    after = datetime.now(UTC) + timedelta(seconds=2)
    updated = machine.transition(
        task.id,
        TaskState.TRIAGED,
        AGENT,
        classification="bug",
        priority="high",
        summary="Checkout fails after login.",
    )
    stamps = [
        task.created_at,
        task.updated_at,
        updated.updated_at,
        machine.list_events(task.id)[0].created_at,
    ]
    assert updated.created_at == task.created_at
    for stamp in stamps:
        assert stamp.endswith("Z")
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        assert parsed.tzinfo == UTC
        assert before <= parsed <= after
