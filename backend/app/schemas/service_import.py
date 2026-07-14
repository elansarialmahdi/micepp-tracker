from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ImportColumn(BaseModel):
    index: int
    name: str


class ImportUploadResponse(BaseModel):
    id: UUID
    filename: str
    columns: list[ImportColumn]
    sample_rows: list[list[str]]
    row_count: int
    ai_categorization_available: bool


class ImportMappingRequest(BaseModel):
    name_column: int = Field(ge=0)
    version_column: int | None = Field(default=None, ge=0)
    category_column: int | None = Field(default=None, ge=0)
    category_mode: Literal["from_file", "uncategorized", "ai"] = "from_file"

    @model_validator(mode="after")
    def unique_columns(self) -> "ImportMappingRequest":
        selected = [
            column
            for column in (self.name_column, self.version_column, self.category_column)
            if column is not None
        ]
        if len(selected) != len(set(selected)):
            raise ValueError("Une colonne ne peut pas être utilisée pour plusieurs champs.")
        if self.category_mode in {"uncategorized", "ai"}:
            self.category_column = None
        return self


class ImportPreviewRow(BaseModel):
    row_number: int
    name: str
    version: str | None
    category: str | None
    status: Literal["valid", "invalid", "duplicate"]
    duplicate_kind: Literal["file", "existing"] | None = None
    errors: list[str] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    id: UUID
    rows: list[ImportPreviewRow]
    valid_count: int
    invalid_count: int
    duplicate_count: int


class ImportConfirmRequest(BaseModel):
    ignored_rows: list[int] = Field(default_factory=list, max_length=1000)
    duplicate_strategy: Literal["ignore", "merge"] = "ignore"
    category_overrides: dict[int, str | None] = Field(default_factory=dict)


class ImportConfirmResponse(BaseModel):
    created: int
    merged: int
    skipped: int
    invalid: int
    categories_created: int
