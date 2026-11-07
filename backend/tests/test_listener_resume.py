"""Resume: same connection id, cursor on pong, and start_from after a drop."""

import asyncio
import logging
from urllib.parse import parse_qs, urlparse

import pytest

from app.agent.listener import RoomListener, StageResult
from app.integrations.switch_client import SwitchClient
from tests.fakes import (
    DROP,
    END,
    FakeDecider,
    FakeIntake,
    FakeTask,
    FakeTransport,
    ScriptedSession,
    connection_state,
    message,
    ping,
)

AGENT_ID = "agent-1"
ROOM_ID = "room-demo"
CONNECTION_ID = "11111111-1111-4111-8111-111111111111"
API_KEY = "test-key"
SWITCH_ROOM_ID = ROOM_ID

ISSUE = """@devteam investigate
Repo: https://github.com/acme/widgets
Ref: main

Checkout API returns HTTP 500 after user login.
"""


def test_reconnect_reuses_connection_id_cursor_and_task_lock() -> None:
    """A drop mid-stage reconnects with the same id and start_from. The lock is held."""

    async def scenario() -> None:
        release = asyncio.Event()
        transitions: list[str] = []
        seen: list[str] = []

        async def stage(task: FakeTask) -> StageResult:
            seen.append(task.id)
            await release.wait()
            transitions.append(task.id)
            return None

        transport = FakeTransport(
            [
                ScriptedSession(
                    [
                        [connection_state(cursor="1", generation=3)],
                        [_issue(seq=2, message_id="m-2")],
                        DROP,
                    ]
                ),
                ScriptedSession([END]),
            ]
        )
        listener = _listener(transport, stage=stage)
        ready = transport.second_connect_event()
        runner = asyncio.create_task(listener.run())
        await ready.wait()
        assert seen
        assert listener.task_lock(seen[0]).locked()
        assert listener.generation == 3
        assert listener.cursor == "2"
        assert len(transport.connections) == 2
        first = _query(str(transport.connections[0]["url"]))
        second = _query(str(transport.connections[1]["url"]))
        assert first["connection_id"] == [CONNECTION_ID]
        assert second["connection_id"] == [CONNECTION_ID]
        assert "start_from" not in first
        assert second["start_from"] == ["2"]
        assert first["room_id"] == [SWITCH_ROOM_ID]
        assert second["room_id"] == [SWITCH_ROOM_ID]
        assert first["scope"] == ["single"]
        assert second["filter"] == ["addressed"]
        assert transport.connections[0]["headers"]["Authorization"] == f"Bearer {API_KEY}"
        release.set()
        await runner
        assert transitions == [seen[0]]

    asyncio.run(scenario())


def test_ping_pong_includes_cursor_and_does_not_cancel_the_stage() -> None:
    """A ping during a stage is a pong with the cursor. The stage still finishes."""

    async def scenario() -> None:
        release = asyncio.Event()
        finished: list[str] = []
        cancelled: list[bool] = []

        async def stage(_task: FakeTask) -> None:
            try:
                await release.wait()
                finished.append("done")
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        transport = FakeTransport(
            [
                ScriptedSession(
                    [
                        [connection_state(cursor="8")],
                        [_issue(seq=9, message_id="m-9")],
                        [ping()],
                        END,
                    ]
                )
            ]
        )
        listener = _listener(transport, stage=stage)
        pong = transport.pong_event()
        runner = asyncio.create_task(listener.run())
        await pong.wait()
        assert finished == []
        assert cancelled == []
        assert transport.outbound[-1] == {"type": "pong", "cursor": "9"}
        release.set()
        await runner
        assert finished == ["done"]
        assert cancelled == []
        assert listener.cursor == "9"

    asyncio.run(scenario())


def test_events_at_or_below_cursor_are_ignored_in_seq_order() -> None:
    """History at or below the cursor is skipped. Newer messages run once, by seq."""

    async def scenario() -> None:
        burst = [
            connection_state(cursor="2", generation=4),
            _issue(seq=4, message_id="m-a"),
            _issue(seq=1, message_id="m-b"),
            _issue(seq=2, message_id="m-c"),
            _issue(seq=3, message_id="m-d"),
        ]
        replay = [
            _issue(seq=5, message_id="m-d"),
            _issue(seq=6, message_id="m-e"),
        ]
        transport, intake, listener = _stack(
            [ScriptedSession([burst, replay, END])]
        )
        await listener.run()
        assert [call["message_id"] for call in intake.calls] == ["m-d", "m-a", "m-e"]
        assert len(transport.posted) == 3
        assert listener.cursor == "6"
        assert listener.generation == 4

    asyncio.run(scenario())


def test_socket_without_room_claims_before_acting() -> None:
    """Events buffered before SWITCH_ROOM_ID is claimed are not a fresh issue."""

    async def scenario() -> None:
        early = _issue(seq=4, message_id="early")
        later = _issue(seq=2, message_id="later")
        transport, intake, listener = _stack(
            [
                ScriptedSession(
                    [[connection_state(cursor="1")], [later], END],
                    preclaim=[early],
                )
            ],
            include_room_on_url=False,
        )
        await listener.run()
        assert transport.discarded[0]["message_id"] == "early"
        assert [call["message_id"] for call in intake.calls] == ["later"]
        opened = _query(str(transport.connections[0]["url"]))
        assert "room_id" not in opened
        assert opened["connection_id"] == [CONNECTION_ID]
        claim = next(
            call
            for call in transport.http_calls
            if str(call["path"]).endswith("/ops/connect_to_room")
        )
        assert claim["method"] == "POST"
        assert claim["headers"]["Authorization"] == f"Bearer {API_KEY}"
        body = claim["json"]
        assert isinstance(body, dict)
        assert body["room_id"] == SWITCH_ROOM_ID
        assert body["connection_id"] == CONNECTION_ID
        paths = [str(call["path"]) for call in transport.http_calls]
        assert paths[0].endswith("/ops/connect_to_room")

    asyncio.run(scenario())


def test_rejected_api_key_backs_off_without_a_task(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Auth failure is logged and backed off. No task is created."""

    async def scenario() -> tuple[list[float], FakeTransport, FakeIntake]:
        slept: list[float] = []

        async def record(seconds: float) -> None:
            slept.append(seconds)

        transport = FakeTransport([], reject_auth=True)
        intake = FakeIntake()
        listener = _listener(
            transport,
            intake=intake,
            sleep=record,
            auth_failure_limit=1,
            backoff_seconds=0.25,
        )
        await listener.run()
        return slept, transport, intake

    caplog.set_level(logging.ERROR, logger="devteam.listener")
    slept, transport, intake = asyncio.run(scenario())
    assert slept == [0.25]
    assert intake.calls == []
    assert transport.posted == []
    assert "authentication failure" in caplog.text


def test_failed_post_after_stage_retries_without_running_the_stage_again() -> None:
    """A failed post is retried. The stage that already finished is not called again."""

    async def scenario() -> None:
        calls: list[str] = []

        async def classify(task: FakeTask) -> StageResult:
            calls.append(task.id)
            return StageResult(reply="Classification ready")

        transport, intake, listener = _stack(
            [
                ScriptedSession(
                    [
                        [connection_state(cursor="1")],
                        [_issue(seq=2, message_id="m-2")],
                        END,
                    ]
                )
            ],
            stage=classify,
        )
        transport.fail_texts["Classification ready"] = 1
        await listener.run()
        assert len(calls) == 1
        assert len(intake.calls) == 1
        assert transport.post_attempts.count("Classification ready") == 2
        assert [item[1] for item in transport.posted].count("Classification ready") == 1

    asyncio.run(scenario())


def test_client_operations_send_bearer_auth() -> None:
    """post_message, read_context, connect_to_room, and list_participants use bearer auth."""
    transport = FakeTransport([])
    transport.contexts[ROOM_ID] = ["oldest", "newest"]
    transport.participants[ROOM_ID] = ["human-1", "agent-1"]
    client = SwitchClient("http://switch.test", AGENT_ID, API_KEY, transport=transport)
    assert client.post_message(ROOM_ID, "hello") == "out-1"
    assert list(client.read_context(ROOM_ID)) == ["oldest", "newest"]
    assert (
        client.connect_to_room(ROOM_ID, connection_id=CONNECTION_ID, start_from="4")
        == CONNECTION_ID
    )
    assert list(client.list_participants(ROOM_ID)) == ["human-1", "agent-1"]
    paths = [str(call["path"]) for call in transport.http_calls]
    assert paths == [
        "/agents/agent-1/ops/post_message",
        "/agents/agent-1/ops/read_context",
        "/agents/agent-1/ops/connect_to_room",
        "/agents/agent-1/ops/list_participants",
    ]
    assert all(call["method"] == "POST" for call in transport.http_calls)
    assert all(
        call["headers"]["Authorization"] == f"Bearer {API_KEY}" for call in transport.http_calls
    )
    claim = transport.http_calls[2]["json"]
    assert isinstance(claim, dict)
    assert claim["start_from"] == "4"
    assert claim["connection_id"] == CONNECTION_ID


def _issue(*, seq: int, message_id: str) -> dict[str, object]:
    return message(
        seq=seq,
        room_id=ROOM_ID,
        message_id=message_id,
        sender_id="human-1",
        text=ISSUE,
        addressed=True,
    )


def _stack(
    sessions: list[ScriptedSession],
    *,
    stage: object | None = None,
    include_room_on_url: bool = True,
) -> tuple[FakeTransport, FakeIntake, RoomListener]:
    transport = FakeTransport(sessions)
    intake = FakeIntake()
    listener = _listener(
        transport,
        intake=intake,
        stage=stage,
        include_room_on_url=include_room_on_url,
    )
    return transport, intake, listener


def _listener(
    transport: FakeTransport,
    *,
    intake: FakeIntake | None = None,
    stage: object | None = None,
    include_room_on_url: bool = True,
    sleep: object | None = None,
    auth_failure_limit: int = 3,
    backoff_seconds: float = 0.0,
) -> RoomListener:
    client = SwitchClient("http://switch.test", AGENT_ID, API_KEY, transport=transport)
    return RoomListener(
        client,
        intake if intake is not None else FakeIntake(),
        agent_id=AGENT_ID,
        connection_id=CONNECTION_ID,
        room_id=ROOM_ID,
        decider=FakeDecider(),
        stage=stage,  # type: ignore[arg-type]
        include_room_on_url=include_room_on_url,
        auth_failure_limit=auth_failure_limit,
        backoff_seconds=backoff_seconds,
        sleep=_no_sleep if sleep is None else sleep,  # type: ignore[arg-type]
    )


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


async def _no_sleep(_seconds: float) -> None:
    return None
