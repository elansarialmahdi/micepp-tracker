from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import httpx

from app.core.config import Settings
from app.services.scan_security import ValidatedScanTarget, validate_scan_target


@dataclass
class Detection:
    name: str
    version: str | None = None
    vendor: str | None = None
    product: str | None = None
    cpe: str | None = None
    source: str = "unknown"
    confidence: float = 0.5
    port: int | None = None
    protocol: str | None = None
    evidence: dict = field(default_factory=dict)


class ServiceDetector(ABC):
    @abstractmethod
    async def detect(self, target: ValidatedScanTarget, settings: Settings) -> list[Detection]: ...


class MockDetector(ServiceDetector):
    async def detect(self, target: ValidatedScanTarget, settings: Settings) -> list[Detection]:
        del target, settings
        return [
            Detection(
                "Nginx",
                "1.26",
                "nginx",
                "nginx",
                source="mock-nmap",
                confidence=0.91,
                port=80,
                protocol="tcp",
                evidence={"kind": "mock-banner"},
            ),
            Detection(
                "Nginx",
                "1.26",
                "nginx",
                "nginx",
                source="mock-web",
                confidence=0.96,
                port=80,
                protocol="tcp",
                evidence={"kind": "mock-header"},
            ),
            Detection(
                "PostgreSQL",
                "16",
                "PostgreSQL",
                "postgresql",
                source="mock-nmap",
                confidence=0.9,
                port=5432,
                protocol="tcp",
                evidence={"kind": "mock-probe"},
            ),
        ]


def _canonical_product_name(product: str) -> str:
    return re.sub(r"\s+(?:httpd|ftpd|pop3d|imapd|smtpd)$", "", product, flags=re.IGNORECASE)


def parse_nmap_detections(payload: bytes) -> list[Detection]:
    root = ElementTree.fromstring(payload)
    detections: list[Detection] = []
    for port_node in root.findall(".//port"):
        state = port_node.find("state")
        service = port_node.find("service")
        if state is None or state.get("state") != "open" or service is None:
            continue
        service_name = service.get("name") or "Service réseau"
        product = service.get("product")
        name = _canonical_product_name(product) if product else service_name
        detections.append(
            Detection(
                name=name,
                version=service.get("version") or None,
                vendor=service.get("vendor"),
                product=product,
                cpe=(service.findtext("cpe") or None),
                source="nmap",
                confidence=0.85,
                port=int(port_node.get("portid", "0")) or None,
                protocol=port_node.get("protocol"),
                evidence={"method": service.get("method"), "service": service_name},
            )
        )
    return detections


class NmapDetector(ServiceDetector):
    async def detect(self, target: ValidatedScanTarget, settings: Settings) -> list[Detection]:
        args = [
            settings.nmap_binary,
            "-sT",
            "-sV",
            "--version-intensity",
            "2",
            "--top-ports",
            str(min(settings.scan_max_ports, 1000)),
            "-oX",
            "-",
            "--",
            target.hostname,
        ]
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, _stderr = await asyncio.wait_for(
                process.communicate(), timeout=settings.max_scan_duration_seconds
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("NMAP_TIMEOUT") from None
        if process.returncode != 0:
            raise RuntimeError("NMAP_FAILED")
        return parse_nmap_detections(stdout)


_WHATWEB_INFORMATIONAL_PLUGINS = {
    "content-security-policy",
    "country",
    "cookies",
    "email",
    "favicon",
    "html5",
    "httpserver",
    "httponly",
    "ip",
    "meta-author",
    "meta-refresh-redirect",
    "passwordfield",
    "redirectlocation",
    "script",
    "secure",
    "strict-transport-security",
    "title",
    "uncommonheaders",
    "x-frame-options",
    "x-powered-by",
    "x-xss-protection",
}


def parse_whatweb_detections(payload: bytes, *, port: int) -> list[Detection]:
    """Convert WhatWeb's JSON log into technology detections.

    WhatWeb also reports page metadata (title, IP, cookies, and similar). Those
    entries are deliberately excluded because the inventory expects software
    products, protocols, and web technologies.
    """
    document = json.loads(payload)
    if not isinstance(document, list):
        raise ValueError("WHATWEB_INVALID_JSON")

    detections: list[Detection] = []
    for result in document:
        if not isinstance(result, dict):
            continue
        plugins = result.get("plugins", {})
        if not isinstance(plugins, dict):
            continue
        for name, details in plugins.items():
            if not isinstance(name, str) or name.casefold() in _WHATWEB_INFORMATIONAL_PLUGINS:
                continue
            if name.casefold() == "open-graph-protocol":
                name = "Open Graph"
            details = details if isinstance(details, dict) else {}
            raw_versions = details.get("version", [])
            if isinstance(raw_versions, str):
                raw_versions = [raw_versions]
            versions = [str(value) for value in raw_versions if value not in (None, "")]
            if name == "Open Graph":
                versions = []
            raw_certainty = details.get("certainty", 100)
            try:
                confidence = max(0.0, min(float(raw_certainty) / 100, 1.0))
            except (TypeError, ValueError):
                confidence = 0.8
            detections.append(
                Detection(
                    name=name,
                    version=versions[0] if versions else None,
                    product=name,
                    source="whatweb",
                    confidence=confidence,
                    port=port,
                    protocol="http",
                    evidence={
                        "fingerprint": "whatweb-plugin",
                        "all_versions": versions,
                        "http_status": result.get("http_status"),
                    },
                )
            )
    return detections


class WhatWebDetector(ServiceDetector):
    async def detect(self, target: ValidatedScanTarget, settings: Settings) -> list[Detection]:
        if target.target_type != "url" or not settings.whatweb_enabled:
            return []
        parsed_url = urlsplit(target.value)
        port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
        args = [
            settings.whatweb_binary,
            "--aggression=1",
            "--follow-redirect=never",
            "--max-redirects=0",
            "--max-threads=1",
            f"--open-timeout={min(settings.whatweb_timeout_seconds, 30)}",
            f"--read-timeout={settings.whatweb_timeout_seconds}",
            "--user-agent=MICEPP-Tracker/scan",
            "--color=never",
            "--quiet",
            "--no-errors",
            "--log-json=/dev/stdout",
            target.value,
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _stderr = await asyncio.wait_for(
                process.communicate(), timeout=settings.whatweb_timeout_seconds + 5
            )
        except (FileNotFoundError, OSError):
            # The built-in detector remains available when the optional binary is absent.
            return []
        except TimeoutError:
            process.kill()
            await process.wait()
            return []
        if process.returncode != 0 or not stdout.strip():
            return []
        try:
            return parse_whatweb_detections(stdout, port=port)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []


def _matched_version(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1) if match and match.lastindex else None


def fingerprint_web_technologies(
    headers: Mapping[str, str],
    html: str,
    *,
    port: int,
    assets: Mapping[str, str] | None = None,
) -> list[Detection]:
    decoded = unescape(html)
    lowered = decoded.casefold()
    script_sources = re.findall(
        r"<script\b[^>]*\bsrc\s*=\s*['\"]([^'\"]+)", decoded, flags=re.IGNORECASE
    )
    link_targets = re.findall(
        r"<link\b[^>]*\bhref\s*=\s*['\"]([^'\"]+)", decoded, flags=re.IGNORECASE
    )
    asset_text = "\n".join([*script_sources, *link_targets])
    asset_lowered = asset_text.casefold()
    resource_text = "\n".join((assets or {}).values())
    resource_lowered = resource_text.casefold()
    detections: dict[str, Detection] = {}

    def add(
        name: str,
        *,
        version: str | None = None,
        confidence: float = 0.8,
        evidence: str,
    ) -> None:
        key = name.casefold()
        candidate = Detection(
            name=name,
            version=version,
            product=name,
            source="web-fingerprint",
            confidence=confidence,
            port=port,
            protocol="http",
            evidence={"fingerprint": evidence},
        )
        current = detections.get(key)
        if current is None or (not current.version and candidate.version):
            detections[key] = candidate

    signatures = (
        (
            "Alpine.js",
            "alpinejs" in asset_lowered
            or bool(re.search(r"\bx-(?:data|init|show|model)\s*=", lowered))
            or "flushandstopdeferringmutations" in resource_lowered,
            r"(?:alpinejs|alpine)(?:@|[-.]v?)(\d+(?:\.\d+){1,3})",
        ),
        (
            "Swiper",
            "swiper" in asset_lowered or "new swiper(" in lowered or "swiper" in resource_lowered,
            r"swiper(?:@|[-.]v?)(\d+(?:\.\d+){0,3})",
        ),
        (
            "Axios",
            "axios" in asset_lowered
            or bool(re.search(r"\baxios\.(?:get|post|create)\b", lowered))
            or "axios" in resource_lowered,
            r"axios(?:@|[-.]v?)(\d+(?:\.\d+){0,3})",
        ),
        (
            "Tailwind CSS",
            "tailwind" in asset_lowered
            or "tailwind.config" in lowered
            or "--tw-" in resource_lowered,
            r"tailwind(?:css)?(?:@|[-.]v?)(\d+(?:\.\d+){0,3})",
        ),
    )
    for name, present, version_pattern in signatures:
        if present:
            version = _matched_version(version_pattern, asset_text)
            if name == "Alpine.js" and not version:
                version = _matched_version(
                    r"version\s*:\s*['\"](\d+(?:\.\d+){1,3})['\"]\s*,"
                    r"flushAndStopDeferringMutations",
                    resource_text,
                )
            add(
                name,
                version=version,
                evidence="html-or-static-asset",
                confidence=0.9 if name.casefold() in asset_lowered else 0.78,
            )

    header_text = "\n".join(headers.values()).casefold()
    if "unpkg.com" in asset_lowered:
        add("Unpkg", evidence="asset-host", confidence=0.95)
    if "fonts.bunny.net" in asset_lowered:
        add("Bunny Fonts", evidence="stylesheet-host", confidence=0.95)
    if (
        "fonts.bunny.net" in asset_lowered
        or "b-cdn.net" in asset_lowered
        or "bunnycdn" in header_text
    ):
        add("Bunny CDN", evidence="asset-or-header", confidence=0.85)
    if re.search(r"<meta\b[^>]*(?:property|name)\s*=\s*['\"]og:", lowered):
        add("Open Graph", evidence="meta-property", confidence=0.98)
    if re.search(r"(?:^|[,;\s])h3(?:-|=|\s)", headers.get("alt-svc", ""), re.IGNORECASE):
        add("HTTP/3", evidence="alt-svc-header", confidence=0.95)

    return list(detections.values())


def referenced_web_assets(html: str, base_url: str) -> list[str]:
    scripts = re.findall(r"<script\b[^>]*\bsrc\s*=\s*['\"]([^'\"]+)", html, flags=re.IGNORECASE)
    links = re.findall(r"<link\b[^>]*\bhref\s*=\s*['\"]([^'\"]+)", html, flags=re.IGNORECASE)
    candidates = [*scripts]
    candidates.extend(
        link
        for link in links
        if ".css" in urlsplit(link).path.casefold() or "fonts.bunny.net" in link.casefold()
    )
    result: list[str] = []
    for candidate in candidates:
        absolute = urljoin(base_url, candidate)
        if urlsplit(absolute).scheme not in {"http", "https"} or absolute in result:
            continue
        result.append(absolute)
    return result


async def _read_limited(response: httpx.Response, limit: int) -> bytes:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        remaining = limit - len(body)
        if remaining <= 0:
            break
        body.extend(chunk[:remaining])
        if len(chunk) > remaining:
            break
    return bytes(body)


async def fetch_web_asset(
    client: httpx.AsyncClient, url: str, settings: Settings
) -> tuple[str, str] | None:
    current = url
    for redirect_count in range(settings.scan_max_redirects + 1):
        await validate_scan_target(current, "url", settings)
        async with client.stream(
            "GET", current, headers={"User-Agent": "MICEPP-Tracker/scan"}
        ) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location or redirect_count >= settings.scan_max_redirects:
                    return None
                current = urljoin(current, location)
                continue
            if response.is_error:
                return None
            content_type = response.headers.get("content-type", "").casefold()
            if not any(marker in content_type for marker in ("javascript", "css", "text")):
                return None
            body = await _read_limited(response, settings.web_scan_max_asset_bytes)
            return current, body.decode(response.encoding or "utf-8", errors="replace")
    return None


class WebDetector(ServiceDetector):
    async def detect(self, target: ValidatedScanTarget, settings: Settings) -> list[Detection]:
        if target.target_type != "url":
            return []
        current = target.value
        async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
            for redirect_count in range(settings.scan_max_redirects + 1):
                validated = await validate_scan_target(current, "url", settings)
                if (
                    validated.hostname == target.hostname
                    and validated.addresses != target.addresses
                ):
                    raise RuntimeError("WEB_DNS_REBINDING_BLOCKED")
                async with client.stream(
                    "GET", current, headers={"User-Agent": "MICEPP-Tracker/scan"}
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location or redirect_count >= settings.scan_max_redirects:
                            raise RuntimeError("WEB_REDIRECT_BLOCKED")
                        current = urljoin(current, location)
                        continue
                    detections: list[Detection] = []
                    parsed_url = urlsplit(current)
                    port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
                    server = response.headers.get("server")
                    powered = response.headers.get("x-powered-by")
                    if server:
                        name, _, version = server.partition("/")
                        detections.append(
                            Detection(
                                name=name,
                                version=version or None,
                                product=name,
                                source="web-header",
                                confidence=0.75,
                                port=port,
                                protocol="http",
                                evidence={"header": "server"},
                            )
                        )
                    if powered:
                        name, _, version = powered.partition("/")
                        detections.append(
                            Detection(
                                name=name,
                                version=version or None,
                                product=name,
                                source="web-header",
                                confidence=0.7,
                                port=port,
                                protocol="http",
                                evidence={"header": "x-powered-by"},
                            )
                        )
                    content_type = response.headers.get("content-type", "").casefold()
                    if not content_type or "html" in content_type:
                        body = await _read_limited(response, settings.web_scan_max_body_bytes)
                        encoding = response.encoding or "utf-8"
                        html = body.decode(encoding, errors="replace")
                        assets: dict[str, str] = {}
                        for asset_url in referenced_web_assets(html, current)[
                            : settings.web_scan_max_assets
                        ]:
                            fetched = await fetch_web_asset(client, asset_url, settings)
                            if fetched:
                                resolved_url, content = fetched
                                assets[resolved_url] = content
                        detections.extend(
                            fingerprint_web_technologies(
                                response.headers, html, port=port, assets=assets
                            )
                        )
                    return detections
        return []


def configured_detectors(settings: Settings) -> list[ServiceDetector]:
    if settings.scan_detector_mode == "mock":
        return [MockDetector()]
    if settings.scan_detector_mode == "nmap":
        return [NmapDetector()]
    if settings.scan_detector_mode == "web":
        return [WhatWebDetector(), WebDetector()]
    return [NmapDetector(), WhatWebDetector(), WebDetector()]
