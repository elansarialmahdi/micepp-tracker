from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.core.config import Settings


class ScanTargetRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedScanTarget:
    value: str
    target_type: str
    hostname: str
    addresses: tuple[str, ...]


def _allowed_networks(settings: Settings) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    try:
        return [
            ipaddress.ip_network(value, strict=False) for value in settings.allowed_scan_networks
        ]
    except ValueError as exc:
        raise ScanTargetRejected(
            "SCAN_CONFIGURATION_INVALID", "L’allowlist réseau est invalide."
        ) from exc


def _validate_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address, settings: Settings
) -> None:
    allowlisted = any(address in network for network in _allowed_networks(settings))
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        raise ScanTargetRejected("SCAN_TARGET_BLOCKED", "Cette adresse réseau est interdite.")
    if address.is_private and not (settings.allow_private_network_scans or allowlisted):
        raise ScanTargetRejected(
            "SCAN_PRIVATE_TARGET_BLOCKED", "Les réseaux privés ne sont pas autorisés."
        )


async def validate_scan_target(
    value: str, target_type: str, settings: Settings
) -> ValidatedScanTarget:
    raw = value.strip()
    if target_type == "ip":
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise ScanTargetRejected("SCAN_TARGET_INVALID", "L’adresse IP est invalide.") from exc
        _validate_address(address, settings)
        return ValidatedScanTarget(str(address), "ip", str(address), (str(address),))
    if target_type != "url":
        raise ScanTargetRejected("SCAN_TARGET_INVALID", "Le type de cible doit être URL ou IP.")
    parsed = urlsplit(raw)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ScanTargetRejected(
            "SCAN_TARGET_INVALID", "Seules les URL HTTP et HTTPS sont acceptées."
        )
    if parsed.username or parsed.password:
        raise ScanTargetRejected(
            "SCAN_TARGET_INVALID", "Les identifiants intégrés à l’URL sont interdits."
        )
    try:
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError as exc:
        raise ScanTargetRejected(
            "SCAN_TARGET_INVALID", "Le port de la cible est invalide."
        ) from exc
    try:
        direct = ipaddress.ip_address(parsed.hostname)
        addresses = {str(direct)}
    except ValueError:
        try:
            infos = await asyncio.to_thread(
                socket.getaddrinfo, parsed.hostname, port, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise ScanTargetRejected(
                "SCAN_DNS_FAILED", "La résolution DNS de la cible a échoué."
            ) from exc
        addresses = {info[4][0] for info in infos}
    if not addresses:
        raise ScanTargetRejected("SCAN_DNS_FAILED", "La cible ne possède aucune adresse résolue.")
    for item in addresses:
        _validate_address(ipaddress.ip_address(item), settings)
    normalized = urlunsplit(
        (parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path or "/", parsed.query, "")
    )
    return ValidatedScanTarget(
        normalized, "url", parsed.hostname.casefold(), tuple(sorted(addresses))
    )
