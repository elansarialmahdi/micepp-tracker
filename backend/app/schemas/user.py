from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    permissions: list[str]


class ManagedUserResponse(BaseModel):
    id: UUID
    username: str
    display_name: str
    is_active: bool
    must_change_password: bool
    roles: list[RoleResponse]
    last_login_at: datetime | None
    created_at: datetime


class ManagedUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=1024)
    role_ids: list[UUID] = Field(min_length=1, max_length=1)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().casefold()

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Le nom affiché est obligatoire.")
        return cleaned


class ManagedUserRolesUpdate(BaseModel):
    role_ids: list[UUID] = Field(min_length=1, max_length=1)


class ManagedUserUpdate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    role_ids: list[UUID] = Field(min_length=1, max_length=1)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().casefold()


class ManagedUserPasswordUpdate(BaseModel):
    password: str = Field(min_length=12, max_length=1024)
