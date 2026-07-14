import json
import logging
import re
from datetime import UTC, datetime

SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|cookie|password|passwd|secret|token|api[_-]?key)\b"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s:]+:[^/@\s]+@", re.IGNORECASE)


def redact_text(value: str) -> str:
    value = BEARER_TOKEN.sub("Bearer [REDACTED]", value)
    value = SENSITIVE_ASSIGNMENT.sub(r"\1\2[REDACTED]", value)
    return URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)


class JsonFormatter(logging.Formatter):
    def __init__(self, environment: str = "development") -> None:
        super().__init__()
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "api",
            "environment": self.environment,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for field in (
            "request_id",
            "user_id",
            "client_ip",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "action",
            "result",
            "task_id",
            "scan_id",
        ):
            if hasattr(record, field):
                value = getattr(record, field)
                payload[field] = redact_text(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str, environment: str = "development") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(environment))
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level.upper())
