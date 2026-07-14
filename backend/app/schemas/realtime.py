from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RealtimeSettingsUpdate(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=60, le=31_536_000)
    batch_size: int | None = Field(default=None, ge=1, le=100)
    max_concurrency: int | None = Field(default=None, ge=1, le=10)


class RealtimeSettingsResponse(BaseModel):
    enabled: bool
    interval_seconds: int
    batch_size: int
    max_concurrency: int
    min_interval_seconds: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    updated_at: datetime


class ProtectionJobResponse(BaseModel):
    id: UUID
    trigger: Literal["manual", "scheduled"]
    status: Literal["queued", "running", "succeeded", "partial", "failed", "skipped"]
    total_services: int
    processed_services: int
    succeeded_services: int
    failed_services: int
    new_notifications: int
    current_batch: int
    current_service_names: list[str] = Field(default_factory=list)
    retry_count: int
    error_summary: list
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
