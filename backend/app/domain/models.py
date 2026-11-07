"""Pydantic contracts. SQLite columns match these models."""

import re
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.states import ActorType, TaskState

PRIORITIES: tuple[str, ...] = ("critical", "high", "medium", "low")
VALIDATION_STATUSES: tuple[str, ...] = ("passed", "failed", "error")
DECISIONS: tuple[str, ...] = ("approved", "rejected")
CLASSIFICATION_EXAMPLES: tuple[str, ...] = (
    "bug",
    "regression",
    "test_failure",
    "config",
)

Priority = Literal["critical", "high", "medium", "low"]
ValidationStatus = Literal["passed", "failed", "error"]
Decision = Literal["approved", "rejected"]

_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _canonical_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ValueError("Identifier must be a UUID.") from exc
    return str(parsed)


def _utc_timestamp(value: str) -> str:
    if _UTC_TIMESTAMP.fullmatch(value) is None:
        raise ValueError("Timestamp must be UTC ISO-8601 ending in Z.")
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _uuid_field(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Identifier must be a UUID.")
    return _canonical_uuid(value)


def _timestamp_field(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be UTC ISO-8601 ending in Z.")
    return _utc_timestamp(value)


class Actor(_Strict):
    type: ActorType
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class Task(_Strict):
    id: str
    switch_room_id: str = Field(min_length=1)
    origin_message_id: str = Field(min_length=1)
    repository: str | None = None
    git_ref: str = "main"
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    logs: str | None = None
    classification: str | None = Field(
        default=None,
        description="Examples: " + ", ".join(CLASSIFICATION_EXAMPLES),
    )
    priority: Priority | None = None
    summary: str | None = None
    state: TaskState
    created_at: str
    updated_at: str

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, value: object) -> str:
        return _uuid_field(value)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _times(cls, value: object) -> str:
        return _timestamp_field(value)


class WorkflowEvent(_Strict):
    id: str
    task_id: str
    from_state: TaskState
    to_state: TaskState
    actor_type: ActorType
    actor_id: str = Field(min_length=1)
    actor_name: str = Field(min_length=1)
    payload: dict[str, Any]
    created_at: str

    @field_validator("id", "task_id", mode="before")
    @classmethod
    def _ids(cls, value: object) -> str:
        return _uuid_field(value)

    @field_validator("created_at", mode="before")
    @classmethod
    def _created(cls, value: object) -> str:
        return _timestamp_field(value)


class EvidenceDraft(_Strict):
    path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    excerpt: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _line_order(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must not precede start_line.")
        return self


class FindingEvidence(_Strict):
    id: str
    finding_id: str
    path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    excerpt: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @field_validator("id", "finding_id", mode="before")
    @classmethod
    def _ids(cls, value: object) -> str:
        return _uuid_field(value)


class FindingDraft(_Strict):
    hypothesis: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    uncertainties: str = ""
    evidence: list[EvidenceDraft] = Field(min_length=1)


class Finding(_Strict):
    id: str
    task_id: str
    hypothesis: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    uncertainties: str
    created_at: str
    evidence: list[FindingEvidence] = Field(min_length=1)

    @field_validator("id", "task_id", mode="before")
    @classmethod
    def _ids(cls, value: object) -> str:
        return _uuid_field(value)

    @field_validator("created_at", mode="before")
    @classmethod
    def _created(cls, value: object) -> str:
        return _timestamp_field(value)


class PatchDraft(_Strict):
    diff: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    affected_files: list[str] = Field(min_length=1)
    test_recommendations: list[str] = Field(default_factory=list)


class Patch(_Strict):
    id: str
    task_id: str
    diff: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    affected_files: list[str]
    test_recommendations: list[str]
    created_at: str

    @field_validator("id", "task_id", mode="before")
    @classmethod
    def _ids(cls, value: object) -> str:
        return _uuid_field(value)

    @field_validator("created_at", mode="before")
    @classmethod
    def _created(cls, value: object) -> str:
        return _timestamp_field(value)


class ValidationDraft(_Strict):
    command: str = Field(min_length=1)
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    risks: str = ""
    started_at: str | None = None
    finished_at: str | None = None

    @field_validator("started_at", "finished_at", mode="before")
    @classmethod
    def _optional_time(cls, value: object) -> str | None:
        if value is None:
            return None
        return _timestamp_field(value)


class ValidationRun(_Strict):
    id: str
    task_id: str
    command: str = Field(min_length=1)
    exit_code: int | None
    stdout: str
    stderr: str
    status: ValidationStatus | None
    risks: str
    started_at: str
    finished_at: str | None

    @field_validator("id", "task_id", mode="before")
    @classmethod
    def _ids(cls, value: object) -> str:
        return _uuid_field(value)

    @field_validator("started_at", mode="before")
    @classmethod
    def _started(cls, value: object) -> str:
        return _timestamp_field(value)

    @field_validator("finished_at", mode="before")
    @classmethod
    def _finished(cls, value: object) -> str | None:
        if value is None:
            return None
        return _timestamp_field(value)


class Approval(_Strict):
    id: str
    task_id: str
    decision: Decision
    reviewer_id: str = Field(min_length=1)
    reviewer_name: str = Field(min_length=1)
    switch_message_id: str = Field(min_length=1)
    reason: str | None = None
    created_at: str

    @field_validator("id", "task_id", mode="before")
    @classmethod
    def _ids(cls, value: object) -> str:
        return _uuid_field(value)

    @field_validator("created_at", mode="before")
    @classmethod
    def _created(cls, value: object) -> str:
        return _timestamp_field(value)


class PullRequestSpec(_Strict):
    url: str = Field(min_length=1)
    number: int = Field(ge=1)
    head_branch: str = Field(min_length=1)


class PullRequest(_Strict):
    id: str
    task_id: str
    url: str = Field(min_length=1)
    number: int = Field(ge=1)
    head_branch: str = Field(min_length=1)
    base_ref: str = Field(min_length=1)
    created_at: str

    @field_validator("id", "task_id", mode="before")
    @classmethod
    def _ids(cls, value: object) -> str:
        return _uuid_field(value)

    @field_validator("created_at", mode="before")
    @classmethod
    def _created(cls, value: object) -> str:
        return _timestamp_field(value)
