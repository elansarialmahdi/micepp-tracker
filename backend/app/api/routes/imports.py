from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_permissions
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import User
from app.models.service import Category, Service, ServiceImport, ServiceSource
from app.repositories.platforms import get_platform
from app.schemas.service_import import (
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportMappingRequest,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportUploadResponse,
)
from app.services.audit import record_audit, request_audit_context
from app.services.automatic_checks import enqueue_service_checks
from app.services.categorization import categorization_available, categorize_services
from app.services.excel_import import UnsafeWorkbook, read_xlsx
from app.services.inventory import normalized_name, normalized_version
from app.services.rate_limit import enforce_expensive_limit

router = APIRouter(prefix="/v1", tags=["service-imports"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
Importer = Annotated[User, Depends(require_permissions("service.import"))]
ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def required_import(
    db: AsyncSession, import_id: UUID, user: User, *, status_required: str | None = None
) -> ServiceImport:
    service_import = await db.get(ServiceImport, import_id)
    if service_import is None or service_import.created_by != user.id:
        raise AppError(404, "IMPORT_NOT_FOUND", "L’import est introuvable.")
    if aware(service_import.expires_at) <= datetime.now(UTC):
        raise AppError(410, "IMPORT_EXPIRED", "La préparation de l’import a expiré.")
    if status_required and service_import.status != status_required:
        raise AppError(409, "IMPORT_STATE_INVALID", "L’import n’est pas dans l’état attendu.")
    return service_import


async def read_limited_upload(upload: UploadFile, maximum: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(64 * 1024):
        size += len(chunk)
        if size > maximum:
            raise AppError(413, "IMPORT_FILE_TOO_LARGE", "Le fichier dépasse la taille autorisée.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/platforms/{platform_id}/service-imports",
    response_model=ImportUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_upload(
    platform_id: UUID,
    request: Request,
    db: DBSession,
    user: Importer,
    file: Annotated[UploadFile, File()],
) -> ImportUploadResponse:
    settings: Settings = request.app.state.settings
    await enforce_expensive_limit(
        request,
        scope="import-upload",
        user_id=user.id,
        limit=settings.import_upload_rate_limit,
        window_seconds=settings.expensive_rate_window_seconds,
    )
    platform = await get_platform(db, platform_id)
    if platform is None:
        raise AppError(404, "PLATFORM_NOT_FOUND", "La plateforme est introuvable.")
    if platform.archived_at is not None:
        raise AppError(409, "PLATFORM_ARCHIVED", "Cette plateforme a été supprimée.")
    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if Path(filename).suffix.casefold() != ".xlsx":
        raise AppError(415, "IMPORT_EXTENSION_INVALID", "Seuls les fichiers .xlsx sont acceptés.")
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise AppError(415, "IMPORT_MIME_INVALID", "Le type MIME du fichier est invalide.")
    content = await read_limited_upload(file, settings.import_max_file_bytes)
    if not content.startswith(b"PK\x03\x04"):
        raise AppError(422, "IMPORT_FILE_INVALID", "Le fichier XLSX est invalide.")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as temporary:
            temporary.write(content)
            temp_path = Path(temporary.name)
        try:
            async with asyncio.timeout(settings.import_timeout_seconds):
                columns, rows = await asyncio.to_thread(
                    read_xlsx,
                    temp_path,
                    max_rows=settings.import_max_rows,
                    max_columns=settings.import_max_columns,
                    max_uncompressed_bytes=settings.import_max_uncompressed_bytes,
                )
        except TimeoutError as exc:
            raise AppError(408, "IMPORT_TIMEOUT", "La lecture du classeur a expiré.") from exc
        except UnsafeWorkbook as exc:
            raise AppError(422, "IMPORT_FILE_INVALID", str(exc)) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        await file.close()
    service_import = ServiceImport(
        platform_id=platform_id,
        created_by=user.id,
        original_filename=filename[:255],
        status="uploaded",
        columns=columns,
        raw_rows=rows,
        row_count=len(rows),
    )
    db.add(service_import)
    await db.commit()
    return ImportUploadResponse(
        id=service_import.id,
        filename=service_import.original_filename,
        columns=columns,
        sample_rows=rows[:5],
        row_count=len(rows),
        ai_categorization_available=categorization_available(
            settings.ai_provider, settings.gemini_api_key
        ),
    )


@router.post("/service-imports/{import_id}/preview", response_model=ImportPreviewResponse)
async def import_preview(
    import_id: UUID,
    payload: ImportMappingRequest,
    request: Request,
    db: DBSession,
    user: Importer,
) -> ImportPreviewResponse:
    service_import = await required_import(db, import_id, user)
    maximum_index = len(service_import.columns) - 1
    selected = [payload.name_column, payload.version_column, payload.category_column]
    if any(column is not None and column > maximum_index for column in selected):
        raise AppError(422, "IMPORT_MAPPING_INVALID", "Le mapping contient une colonne inconnue.")
    existing_rows = (
        await db.execute(
            select(Service.normalized_name, Service.normalized_version).where(
                Service.platform_id == service_import.platform_id,
                Service.archived_at.is_(None),
            )
        )
    ).all()
    existing = set(existing_rows)
    ai_categories = (
        categorize_services(
            [raw[payload.name_column].strip()[:300] for raw in service_import.raw_rows],
            request.app.state.settings.ai_provider,
        )
        if payload.category_mode == "ai"
        else {}
    )
    seen: set[tuple[str, str | None]] = set()
    preview: list[dict] = []
    for offset, raw in enumerate(service_import.raw_rows, start=2):
        name = raw[payload.name_column].strip()[:300]
        version_value = (
            raw[payload.version_column].strip() if payload.version_column is not None else ""
        )
        category_value = ""
        if payload.category_column is not None and payload.category_mode == "from_file":
            category_value = raw[payload.category_column].strip()
        elif payload.category_mode == "ai":
            category_value = ai_categories.get(name, "")
        errors: list[str] = []
        if not name:
            errors.append("Nom du service obligatoire.")
        if len(raw[payload.name_column].strip()) > 300:
            errors.append("Nom du service trop long.")
        if len(version_value) > 200:
            errors.append("Version trop longue.")
        if len(category_value) > 200:
            errors.append("Catégorie trop longue.")
        key = (normalized_name(name), normalized_version(version_value or None))
        duplicate_kind = None
        row_status = "invalid" if errors else "valid"
        if not errors and key in seen:
            row_status = "duplicate"
            duplicate_kind = "file"
            errors.append("Doublon dans le fichier.")
        elif not errors and key in existing:
            row_status = "duplicate"
            duplicate_kind = "existing"
            errors.append("Service déjà présent sur la plateforme.")
        if not errors:
            seen.add(key)
        elif duplicate_kind != "file":
            seen.add(key)
        preview.append(
            {
                "row_number": offset,
                "name": name,
                "version": version_value or None,
                "category": category_value or None,
                "status": row_status,
                "duplicate_kind": duplicate_kind,
                "errors": errors,
            }
        )
    service_import.mapping = payload.model_dump()
    service_import.preview_rows = preview
    service_import.status = "previewed"
    await db.commit()
    return ImportPreviewResponse(
        id=service_import.id,
        rows=[ImportPreviewRow(**row) for row in preview],
        valid_count=sum(row["status"] == "valid" for row in preview),
        invalid_count=sum(row["status"] == "invalid" for row in preview),
        duplicate_count=sum(row["status"] == "duplicate" for row in preview),
    )


@router.post("/service-imports/{import_id}/confirm", response_model=ImportConfirmResponse)
async def import_confirm(
    import_id: UUID,
    payload: ImportConfirmRequest,
    request: Request,
    db: DBSession,
    user: Importer,
) -> ImportConfirmResponse:
    service_import = await required_import(db, import_id, user, status_required="previewed")
    rows = service_import.preview_rows or []
    ignored = set(payload.ignored_rows)
    overrides = {
        row_number: (value.strip()[:200] if value and value.strip() else None)
        for row_number, value in payload.category_overrides.items()
    }
    category_names = {
        normalized_name(overrides.get(row["row_number"], row["category"])): overrides.get(
            row["row_number"], row["category"]
        )
        for row in rows
        if overrides.get(row["row_number"], row["category"])
        and row["status"] != "invalid"
        and row["row_number"] not in ignored
    }
    existing_categories = (
        await db.scalars(select(Category).where(Category.archived_at.is_(None)))
    ).all()
    categories = {category.normalized_name: category for category in existing_categories}
    categories_created = 0
    for key, name in category_names.items():
        if key not in categories:
            category = Category(
                name=name,
                normalized_name=key,
                description=None,
            )
            db.add(category)
            categories[key] = category
            categories_created += 1
    await db.flush()
    existing_services = (
        await db.scalars(
            select(Service).where(
                Service.platform_id == service_import.platform_id,
                Service.archived_at.is_(None),
            )
        )
    ).all()
    existing_by_key = {
        (service.normalized_name, service.normalized_version): service
        for service in existing_services
    }
    created = merged = skipped = invalid = 0
    processed: set[tuple[str, str | None]] = set()
    new_services: list[Service] = []
    for row in rows:
        if row["status"] == "invalid":
            invalid += 1
            continue
        if row["row_number"] in ignored:
            skipped += 1
            continue
        key = (normalized_name(row["name"]), normalized_version(row["version"]))
        if key in processed or row.get("duplicate_kind") == "file":
            skipped += 1
            continue
        processed.add(key)
        category_name = overrides.get(row["row_number"], row["category"])
        category = categories.get(normalized_name(category_name)) if category_name else None
        existing = existing_by_key.get(key)
        if existing:
            if payload.duplicate_strategy == "merge":
                if category is not None:
                    existing.category = category
                    existing.category_id = category.id
                details = dict(existing.source_details or {})
                details["last_excel_import_id"] = str(service_import.id)
                existing.source_details = details
                merged += 1
            else:
                skipped += 1
            continue
        service = Service(
            platform_id=service_import.platform_id,
            category=category,
            category_id=category.id if category else None,
            name=row["name"],
            normalized_name=key[0],
            vendor=None,
            product=None,
            version=row["version"],
            normalized_version=key[1],
            source=ServiceSource.EXCEL.value,
            source_details={
                "import_id": str(service_import.id),
                "filename": service_import.original_filename,
                "row_number": row["row_number"],
            },
            created_by=user.id,
        )
        db.add(service)
        new_services.append(service)
        created += 1
    service_import.status = "confirmed"
    service_import.confirmed_at = datetime.now(UTC)
    record_audit(
        db,
        actor_user_id=user.id,
        action="service.import.excel",
        entity_type="service_import",
        entity_id=service_import.id,
        platform_id=service_import.platform_id,
        summary=f"Import Excel confirmé : {created} service(s) créé(s)",
        metadata={
            "created": created,
            "merged": merged,
            "skipped": skipped,
            "invalid": invalid,
            "categories_created": categories_created,
        },
        **request_audit_context(request),
    )
    await db.commit()
    enqueue_service_checks([service.id for service in new_services], request.app.state.settings)
    return ImportConfirmResponse(
        created=created,
        merged=merged,
        skipped=skipped,
        invalid=invalid,
        categories_created=categories_created,
    )
