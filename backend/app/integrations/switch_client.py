"""Switch HTTP operations and the room WebSocket.

Bearer auth is sent on the socket and on every operation. Reconnect uses the
same connection id and ``start_from`` cursor. The listener owns the socket;
this module is the call surface from ``app.ports.Switch``. Tests inject a
transport so this module does not open a live connection.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import quote, urlencode

_SCOPE = "single"
_FILTER = "addressed"


class SwitchError(Exception):
    """Base error for Switch I/O."""


class SwitchAuthError(SwitchError):
    """The agent API key was rejected."""


class SwitchOperationError(SwitchError):
    """An operation failed after the request was sent."""


class ConnectionDropped(Exception):
    """The socket closed. The listener reconnects with the stored cursor."""


class StreamEnded(Exception):
    """The transport has no further sessions for this run."""


class SwitchSocket(Protocol):
    """One WebSocket session."""

    async def recv_batch(self) -> Sequence[Mapping[str, object]]:
        """Return the next events already available on this socket."""
        ...

    async def send(self, payload: Mapping[str, object]) -> None:
        """Send one client frame, such as a pong."""
        ...

    async def discard_pending(self) -> None:
        """Drop events buffered before the room was claimed."""
        ...

    async def close(self) -> None:
        """Close the socket."""
        ...


class SwitchTransport(Protocol):
    """HTTP and WebSocket I/O. Production uses httpx and websockets."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json_body: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        """Perform one HTTP call and return a JSON object."""
        ...

    async def connect(self, url: str, *, headers: Mapping[str, str]) -> SwitchSocket:
        """Open one WebSocket and return its session."""
        ...


class SwitchClient:
    """Room operations and the connection URL for one agent."""

    def __init__(
        self,
        base_url: str,
        agent_id: str,
        api_key: str,
        *,
        transport: SwitchTransport | None = None,
    ) -> None:
        if base_url.strip() == "" or agent_id.strip() == "" or api_key.strip() == "":
            raise ValueError("base_url, agent_id, and api_key are required.")
        self._base_url = base_url.rstrip("/")
        self._agent_id = agent_id.strip()
        self._api_key = api_key.strip()
        self._transport: SwitchTransport = transport if transport is not None else HttpxTransport()

    def post_message(self, room_id: str, text: str) -> str:
        """Post text to a room and return the new message id."""
        try:
            payload = self._operation("post_message", {"room_id": room_id, "text": text})
        except SwitchOperationError:
            payload = self._send_message(room_id, text)
        message_id = payload.get("message_id", payload.get("event_id"))
        if not isinstance(message_id, str) or message_id.strip() == "":
            raise SwitchOperationError("message_id missing")
        return message_id

    def read_context(self, room_id: str) -> Sequence[str]:
        """Return recent room messages, oldest first."""
        payload = self._operation("read_context", {"room_id": room_id})
        return _message_texts(payload)

    def connect_to_room(
        self,
        room_id: str,
        *,
        connection_id: str,
        start_from: str | None = None,
    ) -> str:
        """Claim or resume a room and return the stable connection id."""
        body: dict[str, object] = {"room_id": room_id, "connection_id": connection_id}
        if start_from is not None:
            body["start_from"] = start_from
        self._operation("connect_to_room", body)
        return connection_id

    def list_participants(self, room_id: str) -> Sequence[str]:
        """Return participant ids currently in the room."""
        payload = self._operation("list_participants", {"room_id": room_id})
        return _participant_ids(payload)

    def websocket_url(
        self,
        *,
        connection_id: str,
        start_from: str | None = None,
        room_id: str | None = None,
    ) -> str:
        """Socket URL. The room id is included so catch-up is not skipped."""
        params: list[tuple[str, str]] = [
            ("connection_id", connection_id),
            ("scope", _SCOPE),
            ("filter", _FILTER),
        ]
        if room_id is not None:
            params.append(("room_id", room_id))
            params.append(("rooms", room_id))
        if start_from is not None:
            params.append(("start_from", start_from))
        agent = quote(self._agent_id, safe="")
        return f"{_ws_base(self._base_url)}/agents/{agent}/connection/ws?{urlencode(params)}"

    async def open_socket(self, url: str) -> SwitchSocket:
        """Open the room socket with bearer auth."""
        return await self._transport.connect(url, headers=self._headers())

    def _operation(self, name: str, body: Mapping[str, object]) -> Mapping[str, object]:
        agent = quote(self._agent_id, safe="")
        url = f"{self._base_url}/agents/{agent}/ops/{name}"
        try:
            payload = self._transport.request(
                "POST",
                url,
                headers=self._headers(),
                json_body=dict(body),
            )
        except SwitchAuthError:
            raise
        except SwitchOperationError:
            raise
        except Exception as exc:
            raise SwitchOperationError(str(exc)) from exc
        if not isinstance(payload, Mapping):
            raise SwitchOperationError(f"{name} returned an unexpected response.")
        return payload

    def _send_message(self, room_id: str, text: str) -> Mapping[str, object]:
        """Post through the message route when the operation body is refused."""
        agent = quote(self._agent_id, safe="")
        url = f"{self._base_url}/agents/{agent}/message"
        try:
            payload = self._transport.request(
                "POST",
                url,
                headers=self._headers(),
                json_body={"room_id": room_id, "content": text},
            )
        except SwitchAuthError:
            raise
        except SwitchOperationError:
            raise
        except Exception as exc:
            raise SwitchOperationError(str(exc)) from exc
        if not isinstance(payload, Mapping):
            raise SwitchOperationError("message returned an unexpected response.")
        return payload

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}


class HttpxTransport:
    """Live transport. Tests do not construct this; they inject a fake."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json_body: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        import httpx

        try:
            response = httpx.request(
                method,
                url,
                headers=dict(headers),
                json=None if json_body is None else dict(json_body),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise SwitchOperationError(str(exc)) from exc
        if response.status_code == 401:
            raise SwitchAuthError("agent API key rejected")
        if response.status_code >= 400:
            raise SwitchOperationError(f"{method} {url} failed with {response.status_code}")
        data: object = response.json()
        if not isinstance(data, dict):
            raise SwitchOperationError("expected a JSON object")
        return {str(key): value for key, value in data.items()}

    async def connect(self, url: str, *, headers: Mapping[str, str]) -> SwitchSocket:
        import inspect
        import websockets

        header_map = dict(headers)
        parameters = inspect.signature(websockets.connect).parameters
        kwargs: dict[str, Any] = {}
        if "additional_headers" in parameters:
            kwargs["additional_headers"] = header_map
        else:
            kwargs["extra_headers"] = header_map
        connection = await websockets.connect(url, **kwargs)
        return _WebSocketSocket(connection)


class _WebSocketSocket:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def recv_batch(self) -> list[dict[str, object]]:
        import websockets

        try:
            raw: object = await self._connection.recv()
        except websockets.exceptions.ConnectionClosed as exc:
            raise ConnectionDropped() from exc
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise SwitchOperationError("socket event must be text")
        parsed: object = json.loads(raw)
        if not isinstance(parsed, dict):
            raise SwitchOperationError("socket event must be an object")
        return [{str(key): value for key, value in parsed.items()}]

    async def send(self, payload: Mapping[str, object]) -> None:
        await self._connection.send(json.dumps(dict(payload)))

    async def discard_pending(self) -> None:
        return None

    async def close(self) -> None:
        await self._connection.close()


def _ws_base(base_url: str) -> str:
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://") :]
    if base_url.startswith("http://"):
        return "ws://" + base_url[len("http://") :]
    return base_url


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise SwitchOperationError(f"{key} missing")
    return value


def _message_texts(payload: Mapping[str, object]) -> list[str]:
    raw = payload.get("messages", [])
    if not isinstance(raw, list):
        raise SwitchOperationError("messages missing")
    texts: list[str] = []
    for item in raw:
        if isinstance(item, str):
            texts.append(item)
            continue
        if isinstance(item, Mapping):
            text = item.get("text", item.get("body", ""))
            if isinstance(text, str):
                texts.append(text)
    return texts


def _participant_ids(payload: Mapping[str, object]) -> list[str]:
    raw = payload.get("participants", [])
    if not isinstance(raw, list):
        raise SwitchOperationError("participants missing")
    ids: list[str] = []
    for item in raw:
        if isinstance(item, str):
            ids.append(item)
            continue
        if isinstance(item, Mapping):
            participant_id = item.get("id")
            if isinstance(participant_id, str):
                ids.append(participant_id)
    return ids
