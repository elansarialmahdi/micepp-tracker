from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.platform import PlatformTargetType


class PlatformCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    target_type: PlatformTargetType = PlatformTargetType.NONE
    target_value: str | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Le nom est obligatoire.")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class PlatformUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    target_type: PlatformTargetType | None = None
    target_value: str | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Le nom est obligatoire.")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class PlatformResponse(BaseModel):
    id: UUID
    name: str
    target_type: PlatformTargetType
    target_value: str | None
    normalized_target: str | None
    description: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    last_inventory_scan_at: datetime | None
    last_vulnerability_check_at: datetime | None
    archived_at: datetime | None
    service_count: int = 0
    threat_count: int = 0

    model_config = {"from_attributes": True}


class PlatformListResponse(BaseModel):
    items: list[PlatformResponse]
    total: int
    page: int
    page_size: int


PlatformSort = Literal["created_at", "-created_at", "name", "-name"]
