from typing import Literal

from pydantic import BaseModel


class ComponentHealth(BaseModel):
    status: Literal["up", "down"]
    detail: str | None = None


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, ComponentHealth]
