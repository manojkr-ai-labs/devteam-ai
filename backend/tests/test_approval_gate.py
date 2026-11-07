"""Approval is a single human decision, and an empty delivery token never calls GitHub."""

import asyncio
import inspect
import urllib.request
from collections.abc import Mapping, Sequence

import pytest

from app.agent.listener import RoomListener
from app.agent.parser import parse_message
from app.domain.errors import DomainError, InvalidTransition
from app.domain.models import Actor, EvidenceDraft, FindingDraft, PatchDraft, Task, ValidationDraft
from app.domain.states import ActorType, TaskState
from app.integrations.switch_client import StreamEnded
from app.persistence.db import connect
from app.persistence.repository import StateMachine
from app.services.approval import ApprovalService
from app.services.intake import IntakeResult

AGENT = "agent-1"
HUMAN = "human-1"
ROOM = "room-1"
CONNECTION = "11111111-1111-1111-1111-111111111111"
_NOT_CONFIGURED = "Pull-request creation is not configured."
Shot = tuple[Task, object, list[object]]


def test_missing_reviewer_writes_no_approval(tmp_path: pytest.TempPathFactory) -> None:
    machine = _machine(tmp_path)
    service = _service(machine, [HUMAN])
    task = _awaiting(machine, "origin-missing")
    shot = _shot(machine, task.id)
    parameters = inspect.signature(ApprovalService.decide).parameters
    assert parameters["reviewer"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        service.decide(task.id, "approved")  # type: ignore[call-arg]
    with pytest.raises(DomainError, match="reviewer"):
        service.decide(task.id, "approved", None, switch_message_id="m-missing")
    _assert_same(machine, task.id, shot)


def test_agent_reviewer_writes_no_approval(tmp_path: pytest.TempPathFactory) -> None:
    machine = _machine(tmp_path)
    service = _service(machine, [AGENT, HUMAN])
    task = _awaiting(machine, "origin-agent")
    shot = _shot(machine, task.id)
    reviewer = Actor(type=ActorType.HUMAN, id=AGENT, name="Ada")
    with pytest.raises(DomainError, match="agent"):
        service.decide(task.id, "approved", reviewer, switch_message_id="m-agent")
    _assert_same(machine, task.id, shot)


def test_non_member_writes_no_approval(tmp_path: pytest.TempPathFactory) -> None:
    machine = _machine(tmp_path)
    service = _service(machine, [HUMAN])
    task = _awaiting(machine, "origin-outsider")
    shot = _shot(machine, task.id)
    reviewer = Actor(type=ActorType.HUMAN, id="outsider", name="Bea")
    with pytest.raises(DomainError, match="participant"):
        service.decide(task.id, "approved", reviewer, switch_message_id="m-outsider")
    _assert_same(machine, task.id, shot)


def test_display_name_spoof_writes_no_approval(tmp_path: pytest.TempPathFactory) -> None:
    machine = _machine(tmp_path)
    service = _service(machine, [{"id": HUMAN, "name": "Ada"}])
    task = _awaiting(machine, "origin-spoof")
    shot = _shot(machine, task.id)
    reviewer = Actor(type=ActorType.HUMAN, id="human-spoof", name="Ada")
    with pytest.raises(DomainError, match="participant"):
        service.decide(task.id, "approved", reviewer, switch_message_id="m-spoof")
    _assert_same(machine, task.id, shot)


def test_wrong_state_writes_no_approval(tmp_path: pytest.TempPathFactory) -> None:
    machine = _machine(tmp_path)
    service = _service(machine, [HUMAN])
    task = machine.create_task(
        switch_room_id=ROOM,
        origin_message_id="origin-received",
        title="Broken login",
        description="Login returns 500.",
        repository="https://github.com/acme/app",
    )
    shot = _shot(machine, task.id)
    with pytest.raises(InvalidTransition):
        service.decide(task.id, "approved", _human(), switch_message_id="m-state")
    _assert_same(machine, task.id, shot)
    assert machine.get_task(task.id).state is TaskState.RECEIVED


def test_repeated_decision_writes_nothing(tmp_path: pytest.TempPathFactory) -> None:
    machine = _machine(tmp_path)
    service = _service(machine, [HUMAN])
    task = _awaiting(machine, "origin-repeat")
    approved = service.decide(task.id, "approved", _human(), switch_message_id="m-once")
    assert approved.state is TaskState.APPROVED
    shot = _shot(machine, task.id)
    with pytest.raises(InvalidTransition):
        service.decide(task.id, "approved", _human(), switch_message_id="m-again")
    _assert_same(machine, task.id, shot)
    with pytest.raises(InvalidTransition):
        service.decide(
            task.id,
            "rejected",
            _human(),
            switch_message_id="m-flip",
            reason="Changed my mind.",
        )
    _assert_same(machine, task.id, shot)
    assert _approval_count(machine, task.id) == 1
    stored = machine.get_approval(task.id)
    assert stored is not None
    assert stored.decision == "approved"
    assert stored.reviewer_id == HUMAN
    assert stored.switch_message_id == "m-once"


def test_rejection_requires_a_reason(tmp_path: pytest.TempPathFactory) -> None:
    machine = _machine(tmp_path)
    service = _service(machine, [HUMAN])
    task = _awaiting(machine, "origin-reason")
    shot = _shot(machine, task.id)
    for reason in (None, "", "   "):
        with pytest.raises(DomainError, match="reason"):
            service.decide(
                task.id,
                "rejected",
                _human(),
                switch_message_id="m-empty",
                reason=reason,
            )
        _assert_same(machine, task.id, shot)
    rejected = service.decide(
        task.id,
        "rejected",
        _human(),
        switch_message_id="m-reason",
        reason="Needs a smaller diff.",
    )
    assert rejected.state is TaskState.REJECTED
    stored = machine.get_approval(task.id)
    assert stored is not None
    assert stored.decision == "rejected"
    assert stored.reason == "Needs a smaller diff."
    assert stored.reviewer_id == HUMAN


@pytest.mark.parametrize("token", ["", "   ", None])
def test_listener_wires_decisions_without_github(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
) -> None:
    if token is None:
        monkeypatch.delenv("GITHUB_DELIVERY_TOKEN", raising=False)
    else:
        monkeypatch.setenv("GITHUB_DELIVERY_TOKEN", token)
    _forbid_github(monkeypatch)
    machine = _machine(tmp_path)
    approve_task = _awaiting(machine, "origin-approve")
    reject_task = _awaiting(machine, "origin-reject")
    cancel_task = _awaiting(machine, "origin-cancel")
    switch = _ScriptedSwitch(
        [
            [
                _event(1, "m-approve", f"@devteam approve {approve_task.id}"),
                _event(2, "m-reject", f"@devteam reject {reject_task.id} The patch is too broad."),
                _event(3, "m-cancel", f"@devteam cancel {cancel_task.id}"),
                _event(4, "m-again", f"@devteam approve {approve_task.id}"),
            ]
        ],
        [HUMAN],
    )
    service = ApprovalService(machine, agent_id=AGENT, participants=switch.list_participants)
    listener = RoomListener(
        switch,  # type: ignore[arg-type]
        _RefuseIntake(),
        agent_id=AGENT,
        connection_id=CONNECTION,
        room_id=ROOM,
        decider=service,
    )
    asyncio.run(listener.run())

    texts = [text for _room, text in switch.posts]
    assert texts[0] == _NOT_CONFIGURED
    assert texts.count(_NOT_CONFIGURED) == 1
    assert "The patch is too broad." in texts
    assert f"Task {cancel_task.id} is CANCELLED." in texts
    assert switch.participant_rooms == [ROOM, ROOM, ROOM, ROOM]
    assert all("github.com" not in text for text in texts)

    approval = machine.get_approval(approve_task.id)
    assert approval is not None
    assert approval.decision == "approved"
    assert approval.reviewer_id == HUMAN
    assert approval.switch_message_id == "m-approve"
    assert _approval_count(machine, approve_task.id) == 1
    assert machine.get_task(approve_task.id).state is TaskState.APPROVED

    rejection = machine.get_approval(reject_task.id)
    assert rejection is not None
    assert rejection.decision == "rejected"
    assert rejection.reason == "The patch is too broad."
    assert machine.get_task(reject_task.id).state is TaskState.REJECTED

    assert machine.get_approval(cancel_task.id) is None
    assert machine.get_task(cancel_task.id).state is TaskState.CANCELLED
    parsed = parse_message(f"@devteam approve {approve_task.id}")
    assert parsed.command is not None


def test_set_token_does_not_call_github(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_DELIVERY_TOKEN", "delivery-token")
    _forbid_github(monkeypatch)
    machine = _machine(tmp_path)
    task = _awaiting(machine, "origin-token")
    service = _service(machine, [HUMAN])
    parsed = parse_message(f"@devteam approve {task.id}")
    assert parsed.command is not None
    reply = service.handle(
        parsed.command,
        room_id=ROOM,
        message_id="m-set",
        sender_id=HUMAN,
        sender_name="Ada",
    )
    assert reply == f"Task {task.id} is APPROVED."
    assert reply is not None
    assert _NOT_CONFIGURED not in reply
    stored = machine.get_approval(task.id)
    assert stored is not None
    assert stored.reviewer_id == HUMAN


def _forbid_github(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GitHub was called")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    try:
        import httpx
    except ModuleNotFoundError:
        return
    monkeypatch.setattr(httpx, "request", boom)
    monkeypatch.setattr(httpx, "post", boom)
    monkeypatch.setattr(httpx.Client, "request", boom)


def _machine(tmp_path: pytest.TempPathFactory) -> StateMachine:
    return StateMachine(str(tmp_path / "state.sqlite"), agent_id=AGENT)  # type: ignore[operator]


def _service(machine: StateMachine, members: Sequence[object]) -> ApprovalService:
    def participants(_room_id: str) -> Sequence[object]:
        return members

    return ApprovalService(machine, agent_id=AGENT, participants=participants)


def _human(reviewer_id: str = HUMAN, name: str = "Ada") -> Actor:
    return Actor(type=ActorType.HUMAN, id=reviewer_id, name=name)


def _awaiting(machine: StateMachine, origin: str) -> Task:
    task = machine.create_task(
        switch_room_id=ROOM,
        origin_message_id=origin,
        title="Broken login",
        description="Login returns 500.",
        repository="https://github.com/acme/app",
    )
    actor = Actor(type=ActorType.AGENT, id=AGENT, name="DevTeam")
    machine.transition(
        task.id,
        TaskState.TRIAGED,
        actor,
        classification="bug",
        priority="high",
        summary="Login fails.",
    )
    machine.transition(task.id, TaskState.INVESTIGATING, actor)
    machine.transition(
        task.id,
        TaskState.PATCH_PROPOSED,
        actor,
        finding=FindingDraft(
            hypothesis="The login handler returns 500.",
            summary="Null user crashes login.",
            recommended_action="Guard the user lookup.",
            evidence=[
                EvidenceDraft(
                    path="app.py",
                    start_line=10,
                    end_line=12,
                    excerpt="user.name",
                    reason="Unchecked user.",
                )
            ],
        ),
        patch=PatchDraft(
            diff="--- a/app.py\n+++ b/app.py\n",
            summary="Guard the user lookup.",
            affected_files=["app.py"],
            test_recommendations=["pytest -q"],
        ),
    )
    machine.transition(task.id, TaskState.VALIDATING, actor, apply_check="git apply --check")
    return machine.transition(
        task.id,
        TaskState.AWAITING_APPROVAL,
        actor,
        validation=ValidationDraft(command="pytest -q", exit_code=0, stdout="ok"),
    )


def _shot(machine: StateMachine, task_id: str) -> Shot:
    return (machine.get_task(task_id), machine.get_approval(task_id), list(machine.list_events(task_id)))


def _assert_same(machine: StateMachine, task_id: str, shot: Shot) -> None:
    assert _shot(machine, task_id) == shot


def _approval_count(machine: StateMachine, task_id: str) -> int:
    conn = connect(machine.database_path, busy_timeout_ms=2000)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM approval WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return int(row["n"])


def _event(seq: int, message_id: str, text: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "addressed": True,
        "message_id": message_id,
        "sender_id": HUMAN,
        "sender_name": "Ada",
        "room_id": ROOM,
        "text": text,
    }
    return {"type": "message", "seq": seq, "room_id": ROOM, "payload": payload}


class _RefuseIntake:
    def receive(
        self,
        *,
        room_id: str,
        message_id: str,
        text: str,
        sender_id: str,
        sender_name: str,
    ) -> IntakeResult:
        raise AssertionError("listener sent a command to intake")


class _ScriptedSocket:
    def __init__(self, batches: list[list[Mapping[str, object]]]) -> None:
        self._batches = batches

    async def recv_batch(self) -> list[Mapping[str, object]]:
        if not self._batches:
            raise StreamEnded()
        return self._batches.pop(0)

    async def send(self, payload: Mapping[str, object]) -> None:
        return None

    async def discard_pending(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _ScriptedSwitch:
    def __init__(self, batches: list[list[Mapping[str, object]]], participants: Sequence[str]) -> None:
        self._socket = _ScriptedSocket(batches)
        self._participants = list(participants)
        self.posts: list[tuple[str, str]] = []
        self.participant_rooms: list[str] = []

    def websocket_url(
        self,
        *,
        connection_id: str,
        start_from: str | None = None,
        room_id: str | None = None,
    ) -> str:
        return "ws://switch.test/room"

    async def open_socket(self, url: str) -> _ScriptedSocket:
        return self._socket

    def post_message(self, room_id: str, text: str) -> str:
        self.posts.append((room_id, text))
        return f"posted-{len(self.posts)}"

    def list_participants(self, room_id: str) -> list[str]:
        self.participant_rooms.append(room_id)
        return list(self._participants)
