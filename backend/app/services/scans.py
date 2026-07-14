from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.scan import DetectedService, ScanJob
from app.services.categorization import categorize_services
from app.services.detectors import Detection, configured_detectors
from app.services.inventory import normalized_name, normalized_version
from app.services.scan_security import ScanTargetRejected, validate_scan_target

logger = logging.getLogger("micepp.scans")


class ScanCancelled(RuntimeError):
    pass


def fuse_detections(items: list[Detection]) -> list[Detection]:
    fused: dict[tuple, Detection] = {}
    for item in items:
        key = (
            normalized_name(item.name),
            normalized_version(item.version),
            (item.vendor or "").casefold(),
            (item.product or "").casefold(),
            item.port,
            item.protocol,
            item.cpe,
        )
        current = fused.get(key)
        if current is None:
            item.evidence = {"sources": [{"detector": item.source, **item.evidence}]}
            fused[key] = item
        else:
            current.confidence = max(current.confidence, item.confidence)
            current.evidence["sources"].append({"detector": item.source, **item.evidence})
            current.source = ",".join(sorted({*current.source.split(","), item.source}))
    return list(fused.values())


async def update_progress(db: AsyncSession, job: ScanJob, progress: int, step: str) -> None:
    await db.refresh(job)
    if job.status == "cancelled":
        raise ScanCancelled
    job.progress = progress
    job.current_step = step
    await db.commit()


async def execute_scan(db: AsyncSession, job: ScanJob, settings: Settings) -> None:
    job.status = "running"
    job.started_at = datetime.now(UTC)
    await db.commit()
    await update_progress(db, job, 5, "validation")
    try:
        target = await validate_scan_target(job.target, job.target_type, settings)
        if tuple(sorted(job.resolved_addresses)) != target.addresses:
            raise ScanTargetRejected(
                "SCAN_DNS_REBINDING_BLOCKED", "La résolution DNS a changé depuis la validation."
            )
        await update_progress(db, job, 20, "résolution")
        detections: list[Detection] = []
        detectors = configured_detectors(settings)
        for index, detector in enumerate(detectors):
            detections.extend(await detector.detect(target, settings))
            await update_progress(
                db, job, 35 + int(30 * (index + 1) / len(detectors)), "détection des services"
            )
        if job.scan_type == "ports":
            detections = [item for item in detections if "web" not in item.source]
        elif job.scan_type == "web":
            detections = [item for item in detections if "web" in item.source]
        fused = fuse_detections(detections)
        await update_progress(db, job, 75, "normalisation")
        categories = categorize_services([item.name for item in fused], settings.ai_provider)
        for item in fused:
            db.add(
                DetectedService(
                    scan_job_id=job.id,
                    detected_name=item.name[:300],
                    detected_version=item.version[:200] if item.version else None,
                    detected_vendor=item.vendor[:300] if item.vendor else None,
                    detected_product=item.product[:300] if item.product else None,
                    detected_cpe=item.cpe[:2048] if item.cpe else None,
                    source_detector=item.source[:100],
                    confidence=max(0, min(item.confidence, 1)),
                    port=item.port,
                    protocol=item.protocol,
                    detection_metadata=item.evidence,
                    category_suggestion=categories.get(item.name),
                    category_confidence=0.75 if item.name in categories else None,
                    selected_for_import=True,
                )
            )
        job.status = "succeeded"
        job.progress = 100
        job.current_step = "résultats prêts"
        job.completed_at = datetime.now(UTC)
        job.raw_result_reference = f"db://scan/{job.id}/detections"
        await db.commit()
    except ScanCancelled:
        await db.rollback()
        return
    except ScanTargetRejected as exc:
        await db.rollback()
        job.status = "failed"
        job.error_code = exc.code
        job.sanitized_error = str(exc)
        job.completed_at = datetime.now(UTC)
        await db.commit()
    except Exception:
        logger.exception("scan_execution_failed", extra={"scan_job_id": str(job.id)})
        await db.rollback()
        job.status = "failed"
        job.error_code = "SCAN_EXECUTION_FAILED"
        job.sanitized_error = "Le détecteur n’a pas pu terminer le scan."
        job.completed_at = datetime.now(UTC)
        await db.commit()
