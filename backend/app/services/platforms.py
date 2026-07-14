import ipaddress
from urllib.parse import urlsplit, urlunsplit

from app.models.platform import PlatformTargetType


class InvalidPlatformTarget(ValueError):
    pass


def normalize_platform_target(
    target_type: PlatformTargetType | str,
    target_value: str | None,
) -> tuple[str | None, str | None]:
    kind = PlatformTargetType(target_type)
    cleaned = target_value.strip() if target_value else None

    if kind is PlatformTargetType.NONE:
        if cleaned:
            raise InvalidPlatformTarget("Une plateforme sans cible ne doit pas contenir d’adresse.")
        return None, None

    if not cleaned:
        label = "L’URL" if kind is PlatformTargetType.URL else "L’adresse IP"
        raise InvalidPlatformTarget(f"{label} est obligatoire pour ce type de cible.")

    if kind is PlatformTargetType.IP:
        try:
            normalized_ip = ipaddress.ip_address(cleaned).compressed
        except ValueError as exc:
            raise InvalidPlatformTarget("L’adresse IP est invalide.") from exc
        return cleaned, normalized_ip

    try:
        parsed = urlsplit(cleaned)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            raise InvalidPlatformTarget("L’URL doit utiliser HTTP ou HTTPS et contenir un hôte.")
        if parsed.username or parsed.password:
            raise InvalidPlatformTarget("Les identifiants ne sont pas autorisés dans l’URL.")
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, InvalidPlatformTarget):
            raise
        raise InvalidPlatformTarget("L’URL est invalide.") from exc

    scheme = parsed.scheme.casefold()
    default_port = 80 if scheme == "http" else 443
    port_suffix = f":{port}" if port and port != default_port else ""
    host = f"[{hostname}]" if ":" in hostname else hostname
    normalized = urlunsplit((scheme, f"{host}{port_suffix}", parsed.path or "/", parsed.query, ""))
    return cleaned, normalized
