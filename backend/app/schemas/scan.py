from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ScanCreate(BaseModel):
    target: str | None = Field(default=None, max_length=2048)
    target_type: Literal["url", "ip"] | None = None
    scan_type: Literal["full", "ports", "web"] = "full"
    authorization_confirmed: bool = True

    @model_validator(mode="after")
    def target_pair(self) -> "ScanCreate":
        if self.target_type and not self.target:
            raise ValueError("La cible temporaire et son type doivent être fournis ensemble.")
        return self


class DetectedServiceResponse(BaseModel):
    id: UUID
    detected_name: str
    detected_version: str | None
    detected_vendor: str | None
    detected_product: str | None
    detected_cpe: str | None
    source_detector: str
    confidence: float
    port: int | None
    protocol: str | None
    category_suggestion: str | None
    category_confidence: float | None
    selected_for_import: bool

    model_config = {"from_attributes": True}


class ScanJobResponse(BaseModel):
    id: UUID
    platform_id: UUID | None
    target: str
    target_type: str
    scan_type: str
    status: str
    progress: int
    current_step: str
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    sanitized_error: str | None
    created_at: datetime
    detections: list[DetectedServiceResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ScanConfirmationItem(BaseModel):
    detected_service_id: UUID
    selected: bool = True
    name: str = Field(min_length=1, max_length=300)
    version: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=200)


class ScanConfirmRequest(BaseModel):
    items: list[ScanConfirmationItem] = Field(min_length=1, max_length=500)


class ScanConfirmResponse(BaseModel):
    created: int
    skipped: int
    categories_created: int
