"""Addressed-only handling, self-post ignore, and (room_id, message_id) dedup."""

import asyncio

from app.agent.listener import RoomListener
from app.agent.parser import CommandName
from app.integrations.switch_client import SwitchClient
from tests.fakes import (
    END,
    FakeDecider,
    FakeIntake,
    FakeTransport,
    ScriptedSession,
    connection_state,
    message,
)

AGENT_ID = "agent-1"
ROOM_ID = "room-1"
CONNECTION_ID = "11111111-1111-4111-8111-111111111111"
API_KEY = "test-key"

ISSUE = """@devteam investigate
Repo: https://github.com/acme/widgets
Ref: main

Checkout API returns HTTP 500 after user login.
"""

APPROVE = "@devteam approve 550e8400-e29b-41d4-a716-446655440000"


def test_unaddressed_messages_create_no_task_and_no_reply() -> None:
    """payload.addressed false does not intake, decide, or post."""

    async def scenario() -> None:
        human = message(
            seq=1,
            room_id=ROOM_ID,
            message_id="m-issue",
            sender_id="human-1",
            text=ISSUE,
            addressed=False,
        )
        command = message(
            seq=2,
            room_id=ROOM_ID,
            message_id="m-approve",
            sender_id="human-1",
            text=APPROVE,
            addressed=False,
        )
        transport, intake, decider, listener = _listener(
            [ScriptedSession([[connection_state(cursor="0")], [human, command], END])]
        )
        await listener.run()
        assert intake.calls == []
        assert decider.calls == []
        assert transport.posted == []

    asyncio.run(scenario())


def test_ignores_the_agents_own_posts() -> None:
    """The agent's sender id and the ids of its own posts are not new work."""

    async def scenario() -> None:
        human = message(
            seq=1,
            room_id=ROOM_ID,
            message_id="m-human",
            sender_id="human-1",
            text=ISSUE,
            addressed=True,
        )
        echo_sender = message(
            seq=2,
            room_id=ROOM_ID,
            message_id="m-echo",
            sender_id=AGENT_ID,
            sender_name="DevTeam",
            text=ISSUE,
            addressed=True,
        )
        echo_id = message(
            seq=3,
            room_id=ROOM_ID,
            message_id="out-1",
            sender_id="human-1",
            text=ISSUE,
            addressed=True,
        )
        _transport, intake, decider, listener = _listener(
            [
                ScriptedSession(
                    [[connection_state(cursor="0")], [human, echo_sender, echo_id], END]
                )
            ]
        )
        await listener.run()
        assert [call["message_id"] for call in intake.calls] == ["m-human"]
        assert decider.calls == []

    asyncio.run(scenario())


def test_duplicate_room_message_does_not_run_twice() -> None:
    """A replayed (room_id, message_id) does not intake or post again."""

    async def scenario() -> None:
        first = message(
            seq=1,
            room_id=ROOM_ID,
            message_id="m-1",
            sender_id="human-1",
            text=ISSUE,
            addressed=True,
        )
        replay = message(
            seq=2,
            room_id=ROOM_ID,
            message_id="m-1",
            sender_id="human-1",
            text=ISSUE,
            addressed=True,
        )
        transport, intake, decider, listener = _listener(
            [ScriptedSession([[connection_state(cursor="0")], [first, replay], END])]
        )
        await listener.run()
        assert [call["message_id"] for call in intake.calls] == ["m-1"]
        assert decider.calls == []
        assert len(transport.posted) == 1
        assert "RECEIVED" in transport.posted[0][1]
        assert listener.cursor == "2"

    asyncio.run(scenario())


def test_addressed_command_reaches_the_decider_once() -> None:
    """Approve is dispatched to the decider, and a replay is not a second decision."""

    async def scenario() -> None:
        first = message(
            seq=1,
            room_id=ROOM_ID,
            message_id="m-cmd",
            sender_id="human-1",
            text=APPROVE,
            addressed=True,
        )
        replay = message(
            seq=2,
            room_id=ROOM_ID,
            message_id="m-cmd",
            sender_id="human-1",
            text=APPROVE,
            addressed=True,
        )
        transport, intake, decider, listener = _listener(
            [ScriptedSession([[connection_state(cursor="0")], [first, replay], END])]
        )
        await listener.run()
        assert intake.calls == []
        assert len(decider.calls) == 1
        assert decider.calls[0].name is CommandName.APPROVE
        assert len(transport.posted) == 1
        assert transport.posted[0][1] == "Received approve."

    asyncio.run(scenario())


def _listener(
    sessions: list[ScriptedSession],
) -> tuple[FakeTransport, FakeIntake, FakeDecider, RoomListener]:
    transport = FakeTransport(sessions)
    intake = FakeIntake()
    decider = FakeDecider()
    client = SwitchClient(
        "http://switch.test",
        AGENT_ID,
        API_KEY,
        transport=transport,
    )
    listener = RoomListener(
        client,
        intake,
        agent_id=AGENT_ID,
        connection_id=CONNECTION_ID,
        room_id=ROOM_ID,
        decider=decider,
        sleep=_no_sleep,
    )
    return transport, intake, decider, listener


async def _no_sleep(_seconds: float) -> None:
    return None
