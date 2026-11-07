"""In-memory Switch transport. These fakes never open a socket or an HTTP connection."""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import uuid4

from app.integrations.switch_client import (
    ConnectionDropped,
    StreamEnded,
    SwitchAuthError,
    SwitchOperationError,
)
from app.services.intake import IntakeResult


class _Signal:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name


DROP = _Signal("DROP")
END = _Signal("END")

SessionStep = list[dict[str, object]] | _Signal


@dataclass
class FakeTask:
    """Stand-in row. The listener only needs the id and the room."""

    id: str
    switch_room_id: str


class ScriptedSession:
    """One socket lifetime. ``preclaim`` is buffered until the listener discards it."""

    def __init__(
        self,
        steps: Sequence[SessionStep],
        *,
        preclaim: Sequence[Mapping[str, object]] | None = None,
    ) -> None:
        self.steps = list(steps)
        self.preclaim = [dict(item) for item in (preclaim or [])]


class FakeTransport:
    """Scripted HTTP and WebSocket. ``reject_auth`` fails before any room event."""

    def __init__(
        self,
        sessions: Sequence[ScriptedSession] | None = None,
        *,
        reject_auth: bool = False,
    ) -> None:
        self.sessions = list(sessions or [])
        self.reject_auth = reject_auth
        self.http_calls: list[dict[str, object]] = []
        self.connections: list[dict[str, object]] = []
        self.outbound: list[dict[str, object]] = []
        self.posted: list[tuple[str, str, str]] = []
        self.post_attempts: list[str] = []
        self.discarded: list[dict[str, object]] = []
        self.fail_texts: dict[str, int] = {}
        self.contexts: dict[str, list[str]] = {}
        self.participants: dict[str, list[str]] = {}
        self.connect_count = 0
        self._next_session = 0
        self._post_count = 0
        self._second_connect: asyncio.Event | None = None
        self._pong_sent: asyncio.Event | None = None

    def second_connect_event(self) -> asyncio.Event:
        if self._second_connect is None:
            self._second_connect = asyncio.Event()
        return self._second_connect

    def pong_event(self) -> asyncio.Event:
        if self._pong_sent is None:
            self._pong_sent = asyncio.Event()
        return self._pong_sent

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json_body: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        if self.reject_auth:
            raise SwitchAuthError("agent API key rejected")
        body = dict(json_body or {})
        path = url.split("?", 1)[0]
        if "://" in path:
            path = "/" + path.split("/", 3)[-1]
        self.http_calls.append(
            {
                "method": method,
                "url": url,
                "path": path,
                "headers": dict(headers),
                "json": body,
            }
        )
        if path.endswith("/ops/post_message"):
            return self._post_message(body)
        if path.endswith("/ops/read_context"):
            room_id = str(body.get("room_id", ""))
            return {"messages": list(self.contexts.get(room_id, []))}
        if path.endswith("/ops/connect_to_room"):
            return {"connection_id": body.get("connection_id", "")}
        if path.endswith("/ops/list_participants"):
            room_id = str(body.get("room_id", ""))
            return {"participants": list(self.participants.get(room_id, []))}
        raise SwitchOperationError(f"unknown operation {path}")

    async def connect(self, url: str, *, headers: Mapping[str, str]) -> object:
        self.connections.append({"url": url, "headers": dict(headers)})
        self.connect_count += 1
        if self.connect_count >= 2:
            self.second_connect_event().set()
        if self.reject_auth:
            raise SwitchAuthError("agent API key rejected")
        if self._next_session >= len(self.sessions):
            raise StreamEnded()
        session = self.sessions[self._next_session]
        self._next_session += 1
        return _ScriptedSocket(session, self)

    def _post_message(self, body: Mapping[str, object]) -> Mapping[str, object]:
        text = body.get("text")
        room_id = body.get("room_id")
        message_text = text if isinstance(text, str) else ""
        room = room_id if isinstance(room_id, str) else ""
        self.post_attempts.append(message_text)
        remaining = self.fail_texts.get(message_text, 0)
        if remaining > 0:
            self.fail_texts[message_text] = remaining - 1
            raise SwitchOperationError("post_message failed")
        self._post_count += 1
        message_id = f"out-{self._post_count}"
        self.posted.append((room, message_text, message_id))
        return {"message_id": message_id}


class _ScriptedSocket:
    def __init__(self, session: ScriptedSession, transport: FakeTransport) -> None:
        self._steps = session.steps
        self._preclaim = session.preclaim
        self._transport = transport
        self._index = 0
        self._closed = False

    async def recv_batch(self) -> list[dict[str, object]]:
        if self._preclaim:
            batch = self._preclaim
            self._preclaim = []
            return batch
        if self._index >= len(self._steps):
            raise ConnectionDropped()
        step = self._steps[self._index]
        self._index += 1
        if step is DROP:
            raise ConnectionDropped()
        if step is END:
            raise StreamEnded()
        if not isinstance(step, list):
            raise ConnectionDropped()
        return [dict(item) for item in step]

    async def send(self, payload: Mapping[str, object]) -> None:
        frame = dict(payload)
        self._transport.outbound.append(frame)
        if frame.get("type") == "pong":
            self._transport.pong_event().set()

    async def discard_pending(self) -> None:
        self._transport.discarded.extend(self._preclaim)
        self._preclaim = []

    async def close(self) -> None:
        self._closed = True


class FakeIntake:
    """Records receive calls. A second call is visible to the dedup tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def receive(
        self,
        *,
        room_id: str,
        message_id: str,
        text: str,
        sender_id: str,
        sender_name: str,
    ) -> IntakeResult:
        self.calls.append(
            {
                "room_id": room_id,
                "message_id": message_id,
                "text": text,
                "sender_id": sender_id,
                "sender_name": sender_name,
            }
        )
        task = FakeTask(id=str(uuid4()), switch_room_id=room_id)
        return IntakeResult(
            outcome="created",
            task=task,  # type: ignore[arg-type]
            reply=f"Task {task.id} is RECEIVED.",
        )


class FakeDecider:
    """Records commands. It does not write an approval."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def handle(
        self,
        command: object,
        *,
        room_id: str,
        message_id: str,
        sender_id: str,
        sender_name: str,
    ) -> str | None:
        self.calls.append(command)
        name = getattr(command, "name", None)
        value = getattr(name, "value", "command")
        return f"Received {value}."


def connection_state(*, cursor: str, generation: int = 1) -> dict[str, object]:
    """A connection_state event that stores this cursor."""
    return {
        "type": "connection_state",
        "cursor": cursor,
        "generation": generation,
        "seq": int(cursor),
    }


def ping() -> dict[str, object]:
    """A server ping. The listener answers with the current cursor."""
    return {"type": "ping"}


def message(
    *,
    seq: int,
    room_id: str,
    message_id: str,
    sender_id: str,
    text: str,
    addressed: bool,
    sender_name: str = "Ada",
) -> dict[str, object]:
    """A room message. ``addressed`` lives only on the payload."""
    return {
        "type": "message",
        "seq": seq,
        "cursor": str(seq),
        "room_id": room_id,
        "message_id": message_id,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "payload": {"addressed": addressed, "text": text},
    }
