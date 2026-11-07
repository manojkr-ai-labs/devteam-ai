import asyncio
import os
from pathlib import Path

from app.agent.listener import RoomListener
from app.integrations.repository import LocalRepository
from app.integrations.switch_client import SwitchClient
from app.persistence.repository import StateMachine
from app.services.approval import ApprovalService
from app.services.intake import IntakeService
from app.services.investigation import InvestigationService

def _load_env() -> None:
    """Fill empty names from a local .env. Existing variables stay as they are."""
    candidates = (
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    )
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "" or stripped.startswith("#") or "=" not in stripped:
                continue
            name, raw = stripped.split("=", 1)
            name = name.strip()
            if name == "" or os.environ.get(name, "").strip() != "":
                continue
            os.environ[name] = raw.strip().strip('"').strip("'")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value == "":
        raise SystemExit(f"{name} is required")
    return value

def build() -> RoomListener:
    _load_env()
    agent_id = _required("SWITCH_AGENT_ID")
    room_id = _required("SWITCH_ROOM_ID")
    database = os.environ.get("DATABASE_PATH", "").strip() or "devteam.db"
    machine = StateMachine(database, agent_id=agent_id)
    client = SwitchClient(_required("SWITCH_BASE_URL"), agent_id, _required("SWITCH_AGENT_API_KEY"))
    repository = LocalRepository(Path(_required("CHECKOUT_PATH")))
    approval = ApprovalService(machine, agent_id=agent_id, participants=client.list_participants)
    return RoomListener(
        client,
        IntakeService(machine, agent_id=agent_id),
        agent_id=agent_id,
        connection_id=_required("SWITCH_CONNECTION_ID"),
        room_id=room_id,
        decider=approval,
        stage=InvestigationService(machine, repository, agent_id=agent_id).run,
    )

def main() -> None:
    asyncio.run(build().run())

if __name__ == "__main__":
    main()
