from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, AwareDatetime

SourceMode = Literal["LIVE_VERIFIED", "REPLAY_VERIFIED", "STANDBY", "BLOCKED"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BeeInput(StrictModel):
    event_id: str = Field(min_length=1, max_length=120)
    utterance: str = Field(min_length=1, max_length=4000)
    speaker: Literal["SELF", "FAMILY_MEMBER", "UNKNOWN"] = "SELF"
    counterparty: str = Field(default="Household", max_length=100)
    occurred_at: AwareDatetime
    timezone: str = "Asia/Kolkata"
    # Bee's own extracted todo (todo-created) carries its alarm as an explicit deadline.
    source_kind: Literal["UTTERANCE", "BEE_TODO", "BEE_TODO_COMPLETED"] = "UTTERANCE"
    due_at: AwareDatetime | None = None


class CameraInput(StrictModel):
    device_id: str = Field(min_length=1, max_length=200)


class RecordedInput(StrictModel):
    fixture: Literal["squats-15", "squats-half-15"] = "squats-15"


class ScenarioInput(StrictModel):
    branch: Literal[
        "deposit",
        "false_claim",
        "unknown",
        "family",
        "retained",
        "visible",
        "empty",
        "ambiguous",
        "engaged",
        "disengaged",
        "real_deposit",
        "real_no_deposit",
        "real_removal",
        "real_pickup",
        "real_passerby",
        "real_visible",
        "real_empty",
        "real_bags",
    ] = "deposit"


class LoginInput(StrictModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class ActionInput(StrictModel):
    action: str = Field(max_length=100)
    revision: int | None = None
    destination: str | None = Field(default=None, max_length=200)
    manifest_hash: str | None = Field(default=None, max_length=64)
    confirmation: str | None = Field(default=None, max_length=200)


class ClockInput(StrictModel):
    minutes: int = Field(ge=1, le=1440)


class ConsentInput(StrictModel):
    enabled: bool


class PoseInput(StrictModel):
    frame_id: str = Field(max_length=100)
    timestamp_ms: int = Field(ge=0)
    landmarks: list[list[float]] = Field(min_length=33, max_length=33)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class ContractRecord(BaseModel):
    """Persisted PSC contract; verification is additionally enforced by domain evidence policy."""

    model_config = ConfigDict(extra="allow")
    contract_id: str
    household_id: str
    key: str
    schema_version: Literal["1.0"]
    actor: dict
    counterparty: dict
    original_utterance: str
    privacy_scope: Literal["HOUSEHOLD"]
    status: Literal[
        "DISCOVERED",
        "NEEDS_CONFIRMATION",
        "ACTIVE",
        "ENGAGED",
        "EVIDENCE_PENDING",
        "DISPUTED",
        "MISSED",
        "VERIFIED",
        "CANCELLED",
        "REJECTED",
    ]
    source_mode: SourceMode
    verification_modality: str
    required_evidence: list[str] = Field(min_length=1)
    evidence_ids: list[str]
    revision: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    due_at: datetime | None
    timezone: str
    deadline_trigger: str | None
    created_at: datetime
    updated_at: datetime
    scheduled_jobs: list[dict]


class EventEnvelope(StrictModel):
    event_id: str
    schema_version: Literal["1.0"]
    event_type: str
    household_id: str
    actor_id: str
    source: str
    source_mode: SourceMode
    occurred_at: AwareDatetime
    received_at: datetime
    trace_id: str
    idempotency_key: str
    consent_scope: str
    payload: dict


class PushKeys(StrictModel):
    p256dh: str = Field(min_length=16, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class PushSubscribeInput(StrictModel):
    endpoint: str = Field(min_length=12, max_length=1000)
    keys: PushKeys


class PushUnsubscribeInput(StrictModel):
    endpoint: str = Field(min_length=12, max_length=1000)


class OwnerPromiseInput(StrictModel):
    """A promise the signed-in owner types into the app (not a Bee capture)."""

    utterance: str = Field(min_length=1, max_length=4000)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
