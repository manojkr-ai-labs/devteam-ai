"""Intake and command-shape tests for the cases edge-case.md assigns here.

Approval and cancel are parsed for a later decider. This phase does not write
those rows or move state for them.
"""

from app.agent.parser import LOG_BYTE_LIMIT, CommandName, ParseKind, parse_message
from app.domain.models import (
    Actor,
    EvidenceDraft,
    FindingDraft,
    PatchDraft,
    ValidationDraft,
)
from app.domain.states import ActorType, TaskState
from app.persistence.repository import StateMachine
from app.ports import GitHubRead, GitHubWrite, Reasoning, Repository, Sandbox, Switch
from app.services.intake import IntakeService
from tests.conftest import AGENT_ID

_ISSUE = """\
@devteam investigate
Repo: https://github.com/acme/checkout
Ref: main

Checkout API returns HTTP 500 after user login.

Traceback (most recent call last):
  File checkout.py
"""

_NO_REPO = """\
@devteam investigate

Checkout API returns HTTP 500 after user login.

Traceback (most recent call last):
  File checkout.py
"""

_TASK = "11111111-1111-4111-8111-111111111111"


def receive(
    machine: StateMachine,
    text: str,
    *,
    room: str = "room-1",
    message: str = "msg-1",
    sender: str = "user-1",
    name: str = "Ada",
):
    return IntakeService(machine, agent_id=AGENT_ID).receive(
        room_id=room,
        message_id=message,
        text=text,
        sender_id=sender,
        sender_name=name,
    )


def _awaiting(machine: StateMachine, task_id: str) -> None:
    agent = Actor(type=ActorType.AGENT, id=AGENT_ID, name="devteam")
    machine.transition(
        task_id,
        TaskState.TRIAGED,
        agent,
        classification="bug",
        priority="high",
        summary="Checkout fails after login.",
    )
    machine.transition(task_id, TaskState.INVESTIGATING, agent)
    machine.transition(
        task_id,
        TaskState.PATCH_PROPOSED,
        agent,
        finding=FindingDraft(
            hypothesis="Checkout reads a session field that login never sets.",
            summary="The handler assumes session.user_id.",
            recommended_action="Set the field during login.",
            evidence=[
                EvidenceDraft(
                    path="checkout.py",
                    start_line=40,
                    end_line=44,
                    excerpt="user_id = session['user_id']",
                    reason="This line raises when login did not store user_id.",
                )
            ],
        ),
        patch=PatchDraft(
            diff="--- a/checkout.py\n+++ b/checkout.py\n@@ -1 +1 @@\n-old\n+new\n",
            summary="Set the session field the checkout handler expects.",
            affected_files=["checkout.py"],
        ),
    )
    machine.transition(
        task_id,
        TaskState.VALIDATING,
        agent,
        apply_check="git apply --check",
    )
    machine.transition(
        task_id,
        TaskState.AWAITING_APPROVAL,
        agent,
        validation=ValidationDraft(command="pytest -q", exit_code=0, stdout="1 passed\n"),
    )


def test_ports_are_the_six_protocols() -> None:
    assert Switch.__name__ == "Switch"
    assert Repository.__name__ == "Repository"
    assert Sandbox.__name__ == "Sandbox"
    assert GitHubRead.__name__ == "GitHubRead"
    assert GitHubWrite.__name__ == "GitHubWrite"
    assert Reasoning.__name__ == "Reasoning"


def test_issue_fields_and_explicit_ref(machine: StateMachine) -> None:
    result = receive(machine, _ISSUE)
    task = result.task
    assert task is not None
    assert result.outcome == "created"
    assert task.state == TaskState.RECEIVED
    assert task.repository == "https://github.com/acme/checkout"
    assert task.git_ref == "main"
    assert task.title == "Checkout API returns HTTP 500 after user login."
    assert task.description == "Checkout API returns HTTP 500 after user login."
    assert task.logs is not None
    assert task.logs.startswith("Traceback")
    assert "checkout.py" in task.logs
    assert task.classification is None
    assert machine.list_events(task.id) == []
    assert task.id in (result.reply or "")


def test_omitted_ref_defaults_to_main(machine: StateMachine) -> None:
    text = """\
@devteam
Repo: https://github.com/acme/checkout

Checkout API returns HTTP 500 after user login.
"""
    result = receive(machine, text)
    assert result.task is not None
    assert result.task.repository == "https://github.com/acme/checkout"
    assert result.task.git_ref == "main"
    assert result.task.state == TaskState.RECEIVED


def test_github_url_without_investigate_is_intake(machine: StateMachine) -> None:
    text = (
        "@devteam https://github.com/acme/checkout "
        "Checkout API returns HTTP 500 after user login."
    )
    result = receive(machine, text)
    assert result.outcome == "created"
    assert result.task is not None
    assert result.task.repository == "https://github.com/acme/checkout"
    assert result.task.git_ref == "main"
    assert result.task.description == "Checkout API returns HTTP 500 after user login."
    assert result.task.logs is None


def test_missing_repository_stays_received_and_asks(machine: StateMachine) -> None:
    result = receive(machine, _NO_REPO)
    task = result.task
    assert task is not None
    assert result.outcome == "needs_repository"
    assert task.state == TaskState.RECEIVED
    assert task.repository is None
    assert task.git_ref == "main"
    assert task.description == "Checkout API returns HTTP 500 after user login."
    assert task.logs is not None and "Traceback" in task.logs
    assert machine.list_events(task.id) == []
    assert machine.get_task(task.id).state == TaskState.RECEIVED
    reply = result.reply or ""
    assert task.id in reply
    assert "repository" in reply.lower()
    assert "Repo:" in reply


def test_follow_up_fills_repository_on_the_same_task(machine: StateMachine) -> None:
    opened = receive(machine, _NO_REPO, message="msg-1")
    assert opened.task is not None
    follow = """\
@devteam
Repo: https://github.com/acme/checkout
"""
    result = receive(machine, follow, message="msg-2")
    assert result.outcome == "repository_filled"
    assert result.task is not None
    assert result.task.id == opened.task.id
    assert result.task.repository == "https://github.com/acme/checkout"
    assert result.task.git_ref == "main"
    assert result.task.state == TaskState.RECEIVED
    assert result.task.description == opened.task.description
    assert result.task.logs == opened.task.logs
    assert len(machine.list_tasks()) == 1
    assert machine.get_by_origin("room-1", "msg-2") is None
    assert machine.list_events(opened.task.id) == []


def test_bare_mention_asks_and_creates_no_task(machine: StateMachine) -> None:
    result = receive(machine, "@devteam")
    assert result.outcome == "needs_issue"
    assert result.task is None
    assert result.reply == "Send the issue and the repository."
    assert machine.list_tasks() == []


def test_unaddressed_and_own_posts_are_ignored(machine: StateMachine) -> None:
    stranger = receive(machine, "please approve the workaround", message="msg-1")
    own = receive(
        machine,
        _ISSUE,
        message="msg-2",
        sender=AGENT_ID,
        name="devteam",
    )
    assert stranger.outcome == "ignored"
    assert stranger.reply is None
    assert own.outcome == "ignored"
    assert own.task is None
    assert machine.list_tasks() == []


def test_replayed_origin_returns_the_same_task(machine: StateMachine) -> None:
    first = receive(machine, _NO_REPO, message="msg-1")
    second = receive(
        machine,
        "@devteam a totally different bug\n\nmore logs",
        message="msg-1",
    )
    assert first.task is not None
    assert second.outcome == "replayed"
    assert second.task is not None
    assert second.task.id == first.task.id
    assert second.task.description == first.task.description
    assert second.task.repository is None
    assert len(machine.list_tasks()) == 1
    assert "repository" in (second.reply or "").lower()


def test_second_issue_does_not_open_another_task(machine: StateMachine) -> None:
    first = receive(machine, _ISSUE, message="msg-1")
    second = receive(
        machine,
        "@devteam Payments fail after refund.\n\nstack line",
        message="msg-2",
    )
    assert first.task is not None
    assert second.outcome == "active_task"
    assert second.task is not None
    assert second.task.id == first.task.id
    assert second.task.state == TaskState.RECEIVED
    reply = second.reply or ""
    assert first.task.id in reply
    assert "Cancel" in reply
    assert "wait" in reply
    assert len(machine.list_tasks()) == 1
    assert machine.get_by_origin("room-1", "msg-2") is None


def test_new_bug_while_awaiting_approval_keeps_that_task(machine: StateMachine) -> None:
    opened = receive(machine, _ISSUE, message="msg-1")
    assert opened.task is not None
    _awaiting(machine, opened.task.id)
    result = receive(
        machine,
        "@devteam Payments fail after refund.\n\nstack line",
        message="msg-2",
    )
    stored = machine.get_task(opened.task.id)
    assert result.outcome == "active_task"
    assert result.task is not None
    assert result.task.id == opened.task.id
    assert stored.state == TaskState.AWAITING_APPROVAL
    assert opened.task.id in (result.reply or "")
    assert len(machine.list_tasks()) == 1


def test_logs_over_64_kib_are_truncated(machine: StateMachine) -> None:
    logs = "L" * (LOG_BYTE_LIMIT + 25)
    text = (
        "@devteam\nRepo: https://github.com/acme/checkout\n\n"
        "Checkout fails.\n\n" + logs
    )
    result = receive(machine, text)
    assert result.logs_truncated is True
    assert result.task is not None
    assert result.task.logs == "L" * LOG_BYTE_LIMIT
    assert "64 KiB" in (result.reply or "")
    assert result.task.state == TaskState.RECEIVED


def test_logs_at_64_kib_stay_whole(machine: StateMachine) -> None:
    logs = "L" * LOG_BYTE_LIMIT
    text = "@devteam\n\nCheckout fails.\n\n" + logs
    result = receive(machine, text)
    assert result.logs_truncated is False
    assert result.task is not None
    assert result.task.logs == logs
    assert "64 KiB" not in (result.reply or "")


def test_mid_sentence_approve_is_intake(machine: StateMachine) -> None:
    text = "@devteam Checkout is broken. Please approve the workaround.\n\nTraceback: boom"
    parsed = parse_message(text)
    assert parsed.kind is ParseKind.ISSUE
    assert parsed.command is None
    assert parsed.issue is not None
    assert "approve" in parsed.issue.description
    result = receive(machine, text)
    assert result.task is not None
    assert result.task.state == TaskState.RECEIVED
    assert machine.get_approval(result.task.id) is None
    assert len(machine.list_tasks()) == 1


def test_non_ascii_lookalike_is_not_a_command(machine: StateMachine) -> None:
    lookalike = "@devteam \u0430pprove the workaround in checkout."
    parsed = parse_message(lookalike)
    assert parsed.kind is ParseKind.ISSUE
    result = receive(machine, lookalike)
    assert result.task is not None
    assert result.outcome == "needs_repository"
    assert machine.get_approval(result.task.id) is None


def test_approve_without_task_id_asks_and_writes_nothing(machine: StateMachine) -> None:
    opened = receive(machine, _ISSUE, message="msg-1")
    assert opened.task is not None
    before = machine.get_task(opened.task.id).updated_at
    result = receive(machine, "@devteam approve", message="msg-2")
    assert result.outcome == "usage"
    assert result.reply == "Send approve <task_id>."
    assert machine.get_approval(opened.task.id) is None
    stored = machine.get_task(opened.task.id)
    assert stored.state == TaskState.RECEIVED
    assert stored.updated_at == before
    assert len(machine.list_tasks()) == 1


def test_cancel_without_task_id_asks_and_does_not_transition(machine: StateMachine) -> None:
    opened = receive(machine, _ISSUE, message="msg-1")
    assert opened.task is not None
    result = receive(machine, "@devteam cancel", message="msg-2")
    assert result.outcome == "usage"
    assert result.reply == "Send cancel <task_id>."
    assert machine.get_task(opened.task.id).state == TaskState.RECEIVED
    assert machine.list_events(opened.task.id) == []


def test_reject_without_reason_leaves_awaiting_approval(machine: StateMachine) -> None:
    opened = receive(machine, _ISSUE, message="msg-1")
    assert opened.task is not None
    _awaiting(machine, opened.task.id)
    result = receive(machine, f"@devteam reject {opened.task.id}", message="msg-2")
    assert result.outcome == "usage"
    assert result.reply == "Send reject <task_id> <reason>."
    assert machine.get_task(opened.task.id).state == TaskState.AWAITING_APPROVAL
    assert machine.get_approval(opened.task.id) is None


def test_approve_command_keeps_task_id_and_optional_reason(machine: StateMachine) -> None:
    opened = receive(machine, _ISSUE, message="msg-1")
    assert opened.task is not None
    _awaiting(machine, opened.task.id)
    text = f"@DevTeam Approve {opened.task.id} looks good"
    parsed = parse_message(text)
    assert parsed.kind is ParseKind.COMMAND
    assert parsed.command is not None
    assert parsed.command.name == CommandName.APPROVE
    assert parsed.command.task_id == opened.task.id
    assert parsed.command.reason == "looks good"
    result = receive(machine, text, message="msg-2")
    assert result.outcome == "command"
    assert result.command is not None
    assert result.command.task_id == opened.task.id
    assert result.command.reason == "looks good"
    recorded: list[tuple[str, str | None]] = []
    recorded.append((result.command.task_id, result.command.reason))
    assert recorded == [(opened.task.id, "looks good")]
    assert machine.get_task(opened.task.id).state == TaskState.AWAITING_APPROVAL
    assert machine.get_approval(opened.task.id) is None


def test_unknown_and_non_uuid_task_ids_reply_task_not_found(machine: StateMachine) -> None:
    opened = receive(machine, _ISSUE, message="msg-1")
    assert opened.task is not None
    before = machine.get_task(opened.task.id).updated_at
    unknown = receive(machine, f"@devteam approve {_TASK}", message="msg-2")
    invalid = receive(machine, "@devteam cancel not-a-uuid", message="msg-3")
    assert unknown.outcome == "task_not_found"
    assert unknown.error_code == "task_not_found"
    assert "task_not_found" in (unknown.reply or "")
    assert invalid.outcome == "task_not_found"
    assert invalid.error_code == "task_not_found"
    assert "not-a-uuid" in (invalid.reply or "")
    stored = machine.get_task(opened.task.id)
    assert stored.state == TaskState.RECEIVED
    assert stored.updated_at == before
    assert machine.get_approval(opened.task.id) is None
    assert len(machine.list_tasks()) == 1


def test_each_room_has_its_own_active_task(machine: StateMachine) -> None:
    first = receive(machine, _ISSUE, room="room-a", message="msg-1")
    second = receive(machine, _NO_REPO, room="room-b", message="msg-2")
    assert first.task is not None and second.task is not None
    assert first.task.id != second.task.id
    assert len(machine.list_tasks()) == 2
