from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationPlatformResponse(BaseModel):
    id: UUID
    name: str


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    severity: str
    vulnerability_id: UUID | None
    service_id: UUID | None
    service_name: str | None
    service_version: str | None
    threat_identifier: str | None
    platform_ids: list[UUID]
    platforms: list[NotificationPlatformResponse]
    created_at: datetime
    read_at: datetime | None
    is_read: bool
    metadata: dict = Field(default_factory=dict)


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int


class AuditEventResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    actor_name: str | None = None
    action: str
    entity_type: str
    entity_id: UUID | None
    platform_id: UUID | None
    summary: str
    before_data: dict | None
    after_data: dict | None
    metadata: dict = Field(default_factory=dict)
    ip: str | None
    request_id: str | None
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int
    page: int
    page_size: int
    success_total: int = 0
    failure_total: int = 0


class ActivityPageViewRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=200)
