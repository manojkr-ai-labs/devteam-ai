"""One room socket: addressed messages, dedup, ping, and resume.

Act only when ``payload.addressed`` is true. Ignore this agent's own posts.
Deduplicate ``(room_id, message_id)``. Reply to every ping with a pong that
includes the cursor. After a drop, reconnect with the same connection id and
``start_from``. Events at or below the stored cursor are ignored.

Commands go to a decider. Until approval and cancel exist, tests inject a fake
decider. Issues go to intake. The task id is posted when intake commits.
Stages after intake run as background tasks under a per-task lock so the
socket keeps answering pings. The lock exists even when the only stage so far
is intake.
"""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.agent.parser import ParseKind, ParsedCommand, parse_message
from app.domain.models import Task
from app.integrations.switch_client import (
    ConnectionDropped,
    StreamEnded,
    SwitchAuthError,
    SwitchClient,
    SwitchOperationError,
    SwitchSocket,
)
from app.services.intake import IntakeResult

logger = logging.getLogger("devteam.listener")

_STAGE_OUTCOMES = frozenset({"created", "needs_repository", "repository_filled"})
_NO_CURSOR = -1

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class StageResult:
    """Text posted after a stage. A failed post retries without running it again."""

    reply: str | None = None


class IntakePort(Protocol):
    """The intake call the listener uses. Approval writes are not included."""

    def receive(
        self,
        *,
        room_id: str,
        message_id: str,
        text: str,
        sender_id: str,
        sender_name: str,
    ) -> IntakeResult:
        """Persist an addressed issue or describe a command."""
        ...


class Decider(Protocol):
    """Command handler. This phase records the command and does not approve."""

    def handle(
        self,
        command: ParsedCommand,
        *,
        room_id: str,
        message_id: str,
        sender_id: str,
        sender_name: str,
    ) -> str | None:
        """Return an optional room reply."""
        ...


class Stage(Protocol):
    """Work after intake. Runs under the per-task lock, off the read loop."""

    def __call__(self, task: Task) -> StageResult | None | Awaitable[StageResult | None]:
        """Advance one task and optionally return text to post."""
        ...


@dataclass(frozen=True)
class RoomEvent:
    """One socket event. ``addressed`` is taken only from ``payload.addressed``."""

    kind: str
    generation: int | None = None
    seq: int | None = None
    room_id: str = ""
    message_id: str = ""
    sender_id: str = ""
    sender_name: str = ""
    text: str = ""
    addressed: bool = False


class RoomListener:
    """Keep one Switch connection and dispatch addressed room messages."""

    def __init__(
        self,
        client: SwitchClient,
        intake: IntakePort,
        *,
        agent_id: str,
        connection_id: str,
        room_id: str,
        decider: Decider | None = None,
        stage: Stage | None = None,
        include_room_on_url: bool = True,
        auth_failure_limit: int = 3,
        backoff_seconds: float = 1.0,
        post_attempts: int = 3,
        post_retry_delay: float = 0.0,
        sleep: Sleep | None = None,
    ) -> None:
        if agent_id.strip() == "" or room_id.strip() == "":
            raise ValueError("agent_id and room_id are required.")
        if auth_failure_limit < 1 or post_attempts < 1:
            raise ValueError("Retry limits must allow at least one attempt.")
        self._client = client
        self._intake = intake
        self._agent_id = agent_id.strip()
        self.connection_id = _canonical_uuid(connection_id)
        self._room_id = room_id.strip()
        self._decider = decider
        self._stage = stage
        self._room_on_url = include_room_on_url
        self._auth_failure_limit = auth_failure_limit
        self._backoff_seconds = backoff_seconds
        self._post_attempts = post_attempts
        self._post_retry_delay = post_retry_delay
        self._sleep_impl = sleep
        self.cursor: str | None = None
        self.generation: int | None = None
        self.auth_failures = 0
        self._cursor_seq = _NO_CURSOR
        self._seen: set[tuple[str, str]] = set()
        self._own_message_ids: set[str] = set()
        self._task_locks: dict[str, asyncio.Lock] = {}
        self._staged: set[str] = set()
        self._stages: set[asyncio.Task[None]] = set()

    def task_lock(self, task_id: str) -> asyncio.Lock:
        """Return the per-task lock, creating it if intake has not run a stage yet."""
        lock = self._task_locks.get(task_id)
        if lock is None:
            lock = asyncio.Lock()
            self._task_locks[task_id] = lock
        return lock

    async def run(self) -> None:
        """Read until the transport ends. A dropped socket resumes in place."""
        try:
            while True:
                try:
                    await self._session()
                except ConnectionDropped:
                    continue
                except StreamEnded:
                    return
                except SwitchAuthError:
                    logger.error("authentication failure")
                    self.auth_failures += 1
                    await self._sleep(self._backoff_seconds)
                    self._backoff_seconds = min(self._backoff_seconds * 2, 30.0)
                    if self.auth_failures >= self._auth_failure_limit:
                        return
        finally:
            await self._drain_stages()

    async def _session(self) -> None:
        room_for_url = self._room_id if self._room_on_url else None
        url = self._client.websocket_url(
            connection_id=self.connection_id,
            start_from=self.cursor,
            room_id=room_for_url,
        )
        socket = await self._client.open_socket(url)
        try:
            if room_for_url is None:
                self._client.connect_to_room(
                    self._room_id,
                    connection_id=self.connection_id,
                    start_from=self.cursor,
                )
                await socket.discard_pending()
                self._room_on_url = True
            while True:
                batch = await socket.recv_batch()
                await self._handle_batch(socket, batch)
        finally:
            await socket.close()

    async def _handle_batch(
        self,
        socket: SwitchSocket,
        batch: Sequence[Mapping[str, object]],
    ) -> None:
        events = [parse_room_event(item) for item in batch]
        for event in events:
            if event.kind == "connection_state":
                self._apply_connection_state(event)
            elif event.kind == "ping":
                await socket.send({"type": "pong", "cursor": self.cursor})
        floor = self._cursor_seq
        messages = [event for event in events if event.kind == "message"]
        messages.sort(
            key=lambda event: (event.seq is None, event.seq if event.seq is not None else 0)
        )
        spawned = False
        for message in messages:
            if message.seq is not None and message.seq <= floor:
                continue
            if await self._handle_message(message):
                spawned = True
        if spawned:
            await asyncio.sleep(0)

    async def _handle_message(self, message: RoomEvent) -> bool:
        """Dispatch one new event. Return whether a stage task was started."""
        if not self._actionable(message):
            self._note_seq(message.seq)
            return False
        key = (message.room_id, message.message_id)
        if key in self._seen:
            self._note_seq(message.seq)
            return False
        reply, task, outcome = self._accept(message)
        self._seen.add(key)
        self._note_seq(message.seq)
        if reply:
            await self._post(message.room_id, reply)
        if task is None or self._stage is None or outcome not in _STAGE_OUTCOMES:
            if task is not None:
                self.task_lock(task.id)
            return False
        self.task_lock(task.id)
        if task.id in self._staged:
            return False
        self._staged.add(task.id)
        self._spawn(task)
        return True

    def _actionable(self, message: RoomEvent) -> bool:
        if message.addressed is not True:
            return False
        if message.sender_id == "" or message.message_id == "" or message.room_id == "":
            return False
        if message.room_id != self._room_id:
            return False
        if message.sender_id == self._agent_id:
            return False
        if message.message_id in self._own_message_ids:
            return False
        return True

    def _accept(self, message: RoomEvent) -> tuple[str | None, Task | None, str]:
        parsed = parse_message(message.text)
        if parsed.kind is ParseKind.COMMAND and parsed.command is not None and self._decider is not None:
            reply = self._decider.handle(
                parsed.command,
                room_id=message.room_id,
                message_id=message.message_id,
                sender_id=message.sender_id,
                sender_name=message.sender_name or message.sender_id,
            )
            return reply, None, "command"
        result = self._intake.receive(
            room_id=message.room_id,
            message_id=message.message_id,
            text=message.text,
            sender_id=message.sender_id,
            sender_name=message.sender_name or message.sender_id,
        )
        if result.outcome in {"replayed", "ignored"}:
            return None, result.task, result.outcome
        return result.reply, result.task, result.outcome

    def _spawn(self, task: Task) -> None:
        stage = self._stage
        if stage is None:
            return
        job = asyncio.create_task(self._run_stage(task, stage))
        self._stages.add(job)
        job.add_done_callback(self._stages.discard)

    async def _run_stage(self, task: Task, stage: Stage) -> None:
        reply: str | None = None
        try:
            async with self.task_lock(task.id):
                outcome = await _invoke_stage(stage, task)
                if isinstance(outcome, StageResult):
                    reply = outcome.reply
            if reply:
                await self._post(task.switch_room_id, reply)
        except SwitchAuthError:
            logger.error("authentication failure")
            self.auth_failures += 1

    async def _post(self, room_id: str, text: str) -> None:
        for attempt in range(self._post_attempts):
            try:
                message_id = self._client.post_message(room_id, text)
            except SwitchOperationError:
                if attempt + 1 >= self._post_attempts:
                    logger.error("post_message failed")
                    return
                await self._sleep(self._post_retry_delay)
                continue
            if message_id.strip():
                self._own_message_ids.add(message_id.strip())
            return

    def _apply_connection_state(self, event: RoomEvent) -> None:
        if event.generation is not None:
            self.generation = event.generation
        if event.seq is not None and (self.cursor is None or event.seq > self._cursor_seq):
            self._set_cursor(event.seq)

    def _note_seq(self, seq: int | None) -> None:
        if seq is None:
            return
        if self.cursor is None or seq > self._cursor_seq:
            self._set_cursor(seq)

    def _set_cursor(self, seq: int) -> None:
        self._cursor_seq = seq
        self.cursor = str(seq)

    async def _sleep(self, seconds: float) -> None:
        if self._sleep_impl is not None:
            await self._sleep_impl(seconds)
            return
        if seconds > 0:
            await asyncio.sleep(seconds)

    async def _drain_stages(self) -> None:
        pending = list(self._stages)
        if not pending:
            return
        results = await asyncio.gather(*pending, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception) and not isinstance(result, SwitchAuthError):
                logger.error("stage failed", exc_info=result)


def parse_room_event(raw: Mapping[str, object]) -> RoomEvent:
    """Build one event. ``addressed`` is true only when that payload flag is true."""
    event_name = raw.get("event")
    data = raw.get("data")
    if isinstance(event_name, str) and isinstance(data, Mapping):
        return _parse_envelope(event_name, data, raw)
    payload = raw.get("payload")
    body = payload if isinstance(payload, Mapping) else {}
    kind = raw.get("type")
    seq = _seq(raw.get("seq"))
    if seq is None:
        seq = _seq(raw.get("cursor"))
    return RoomEvent(
        kind=kind if isinstance(kind, str) else "",
        generation=_generation(raw.get("generation")),
        seq=seq,
        room_id=_field(raw, body, "room_id"),
        message_id=_field(raw, body, "message_id"),
        sender_id=_sender_id(raw, body),
        sender_name=_field(raw, body, "sender_name"),
        text=_event_text(body),
        addressed=body.get("addressed") is True,
    )


def _parse_envelope(
    event_name: str,
    data: Mapping[str, object],
    raw: Mapping[str, object],
) -> RoomEvent:
    """Read a live Switch frame: ``{"event", "data", "id"}``."""
    if event_name == "ping":
        return RoomEvent(kind="ping")
    nested = data.get("payload")
    body = nested if isinstance(nested, Mapping) else data
    seq = _seq(raw.get("id"))
    if seq is None:
        seq = _seq(data.get("sequence"))
    if seq is None:
        seq = _seq(data.get("seq"))
    if seq is None:
        seq = _seq(data.get("cursor"))
    return RoomEvent(
        kind=event_name,
        generation=_generation(data.get("generation")),
        seq=seq,
        room_id=_field(data, body, "room_id"),
        message_id=_field(data, body, "message_id"),
        sender_id=_sender_id(data, body),
        sender_name=_field(data, body, "sender_name"),
        text=_event_text(body),
        addressed=body.get("addressed") is True,
    )


def _sender_id(raw: Mapping[str, object], payload: Mapping[str, object]) -> str:
    sender_id = _field(raw, payload, "sender_id")
    if sender_id != "":
        return sender_id
    return _field(raw, payload, "sender")


async def _invoke_stage(stage: Stage, task: Task) -> StageResult | None:
    outcome = stage(task)
    if inspect.isawaitable(outcome):
        awaited: StageResult | None = await outcome
        return awaited
    return outcome


def _canonical_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError("connection_id must be a UUID.") from exc


def _field(raw: Mapping[str, object], payload: Mapping[str, object], key: str) -> str:
    value = raw.get(key, payload.get(key, ""))
    if not isinstance(value, str):
        return ""
    return value.strip()


def _event_text(payload: Mapping[str, object]) -> str:
    text = payload.get("text")
    if isinstance(text, str):
        return text
    body = payload.get("body")
    if isinstance(body, str):
        return body
    return ""


def _generation(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _seq(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
