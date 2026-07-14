from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from app.core.config import Settings


def enqueue_service_checks(service_ids: Iterable[UUID], settings: Settings) -> None:
    if settings.app_env == "test":
        return
    from app.worker import check_service_task

    for service_id in service_ids:
        check_service_task.delay(str(service_id))
