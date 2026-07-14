from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.service import ServiceSource


def clean_required_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Le nom est obligatoire.")
    return cleaned


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    _clean_name = field_validator("name")(clean_required_name)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return clean_required_name(value) if value is not None else None


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    model_config = {"from_attributes": True}


class AICategorizationInput(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    version: str | None = Field(default=None, max_length=200)
    vendor: str | None = Field(default=None, max_length=300)
    product: str | None = Field(default=None, max_length=300)

    _clean_name = field_validator("name")(clean_required_name)


class AICategorizationRequest(BaseModel):
    items: list[AICategorizationInput] = Field(min_length=1, max_length=1000)


class AICategorizationSuggestion(BaseModel):
    key: str
    category: CategoryResponse
    category_created: bool
    confidence: float = Field(ge=0, le=1)
    reason: str


class AICategorizationResponse(BaseModel):
    items: list[AICategorizationSuggestion]


class AICategorizationPreviewSuggestion(BaseModel):
    key: str
    category_name: str
    existing_category_id: UUID | None = None
    confidence: float = Field(ge=0, le=1)
    reason: str


class AICategorizationPreviewResponse(BaseModel):
    items: list[AICategorizationPreviewSuggestion]


class AICategorizationConfirmItem(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    category_name: str = Field(min_length=1, max_length=200)
    selected: bool = True

    _clean_name = field_validator("category_name")(clean_required_name)


class AICategorizationConfirmRequest(BaseModel):
    items: list[AICategorizationConfirmItem] = Field(min_length=1, max_length=1000)


class AICategorizationConfirmedItem(BaseModel):
    key: str
    category: CategoryResponse


class AICategorizationConfirmResponse(BaseModel):
    items: list[AICategorizationConfirmedItem]


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    version: str | None = Field(default=None, max_length=200)
    category_id: UUID | None = None
    vendor: str | None = Field(default=None, max_length=300)
    product: str | None = Field(default=None, max_length=300)

    _clean_name = field_validator("name")(clean_required_name)

    @field_validator("version", "vendor", "product")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class ServiceBulkCreate(BaseModel):
    items: list[ServiceCreate] = Field(min_length=1, max_length=100)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    version: str | None = Field(default=None, max_length=200)
    category_id: UUID | None = None
    vendor: str | None = Field(default=None, max_length=300)
    product: str | None = Field(default=None, max_length=300)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return clean_required_name(value) if value is not None else None

    @field_validator("version", "vendor", "product")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class ServiceResponse(BaseModel):
    id: UUID
    platform_id: UUID
    category_id: UUID | None
    category_name: str | None
    name: str
    vendor: str | None
    product: str | None
    version: str | None
    cpe_uri: str | None
    cpe_match_confidence: float | None
    cpe_match_method: str | None
    security_identity: dict | None = None
    source: ServiceSource
    first_seen_at: datetime
    last_seen_at: datetime
    last_checked_at: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    active_vulnerability_count: int = 0

    model_config = {"from_attributes": True}


class ServiceListResponse(BaseModel):
    items: list[ServiceResponse]
    total: int
    page: int
    page_size: int
    vulnerable_total: int = 0
    safe_total: int = 0
    unverified_total: int = 0


ServiceSort = Literal["name", "-name", "created_at", "-created_at", "version", "-version"]
