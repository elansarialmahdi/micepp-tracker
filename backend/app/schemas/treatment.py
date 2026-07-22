from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TreatmentUserResponse(BaseModel):
    id: UUID
    username: str
    display_name: str


class TreatmentCreate(BaseModel):
    service_id: UUID
    assigned_to_id: UUID
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class TreatmentSubmit(BaseModel):
    new_version: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("new_version")
    @classmethod
    def clean_version(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("La nouvelle version est obligatoire.")
        return cleaned

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class TreatmentResponse(BaseModel):
    id: UUID
    status: Literal["assigned", "submitted", "confirmed", "cancelled"]
    assignment_note: str | None
    completion_note: str | None
    service_version_before: str | None
    new_version: str | None
    assigned_at: datetime
    submitted_at: datetime | None
    confirmed_at: datetime | None
    service_id: UUID
    service_name: str
    service_version: str | None
    platform_id: UUID
    platform_name: str
    assignee: TreatmentUserResponse | None
    assigned_by: TreatmentUserResponse | None
    confirmed_by: TreatmentUserResponse | None
