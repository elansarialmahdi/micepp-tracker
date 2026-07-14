import json
import logging
from pathlib import Path

from app.core.logging import JsonFormatter, redact_text

ROOT = Path(__file__).resolve().parents[2]


def test_structured_logs_redact_credentials_and_tokens() -> None:
    message = (
        "password=SuperSecret! Authorization: Bearer abc.def.ghi "
        "url=https://admin:private@example.test token=raw-token"
    )
    record = logging.LogRecord(
        name="security-test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter("production").format(record))
    encoded = json.dumps(payload)
    assert payload["environment"] == "production"
    assert "SuperSecret" not in encoded
    assert "abc.def.ghi" not in encoded
    assert "admin:private" not in encoded
    assert "raw-token" not in encoded
    assert encoded.count("REDACTED") >= 4
    assert redact_text("Cookie=session-value") == "Cookie=[REDACTED]"


def test_proxy_declares_required_security_headers_and_limits() -> None:
    config = (ROOT / "infra/reverse-proxy/nginx.conf").read_text(encoding="utf-8")
    for directive in (
        "Content-Security-Policy",
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Cross-Origin-Opener-Policy",
        "client_max_body_size 10m",
        "limit_req zone=api_general",
        "server_tokens off",
    ):
        assert directive in config


def test_csp_allows_vite_only_in_development() -> None:
    development = (ROOT / "infra/reverse-proxy/nginx.conf").read_text(encoding="utf-8")
    production = (ROOT / "infra/reverse-proxy/nginx.prod.conf").read_text(encoding="utf-8")
    assert "script-src 'self' 'unsafe-inline'" in development
    assert "style-src 'self' 'unsafe-inline'" in development
    assert "connect-src 'self' ws: wss:" in development
    assert "'unsafe-inline'" not in production
    assert "connect-src 'self';" in production


def test_compose_uses_official_crs_and_forces_blocking_in_production() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    production = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "owasp/modsecurity-crs:4.25.0-nginx-lts" in compose
    assert "MODSEC_AUDIT_LOG_FORMAT: JSON" in compose
    assert 'MODSEC_AUDIT_LOG_PARTS: "AHZ"' in compose
    assert "${WAF_MODE:-DetectionOnly}" in compose
    assert 'MODSEC_RULE_ENGINE: "On"' in production
    assert 'NGINX_ALWAYS_TLS_REDIRECT: "on"' in production
    assert "TLSv1.2 TLSv1.3" in production
    assert "TLS_CERT_PATH must be configured" in production
    assert "target: production" in production


def test_production_frontend_uses_internal_proxy_port() -> None:
    frontend_nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    proxy = (ROOT / "infra/reverse-proxy/nginx.conf").read_text(encoding="utf-8")
    assert "listen 5173;" in frontend_nginx
    assert "proxy_pass http://frontend:5173;" in proxy
