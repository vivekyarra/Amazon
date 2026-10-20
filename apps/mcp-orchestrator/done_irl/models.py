from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

SourceMode = Literal["LIVE_VERIFIED", "SIMULATED_VERIFIED", "NOT_CONNECTED", "BLOCKED"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BeeInput(StrictModel):
    event_id: str = Field(min_length=1, max_length=120)
    utterance: str = Field(min_length=1, max_length=4000)
    speaker: Literal["SELF", "FAMILY_MEMBER", "UNKNOWN"] = "SELF"
    counterparty: str = Field(default="Household", max_length=100)
    occurred_at: datetime
    timezone: str = "Asia/Kolkata"


class ScenarioInput(StrictModel):
    branch: Literal[
        "deposit",
        "fake",
        "unknown",
        "family",
        "retained",
        "visible",
        "empty",
        "ambiguous",
        "engaged",
        "disengaged",
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
