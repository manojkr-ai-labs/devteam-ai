"""Fixtures for the workflow state machine."""

from pathlib import Path

import pytest

from app.persistence.repository import StateMachine

AGENT_ID = "agent-devteam"


@pytest.fixture
def machine(tmp_path: Path) -> StateMachine:
    return StateMachine(str(tmp_path / "devteam.db"), agent_id=AGENT_ID)
