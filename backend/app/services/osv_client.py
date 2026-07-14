from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings

ECOSYSTEMS = ("npm", "PyPI", "NuGet", "RubyGems", "crates.io")
DEPS_SYSTEMS = {
    "npm": "npm",
    "PyPI": "pypi",
    "NuGet": "nuget",
    "RubyGems": "rubygems",
    "crates.io": "cargo",
}
PACKAGE_ALIASES = {
    "axios.js": "axios",
    "react.js": "react",
    "vue.js": "vue",
    "jquery": "jquery",
    "django": "django",
}


@dataclass(frozen=True)
class PackageIdentity:
    ecosystem: str
    name: str
    version: str


def package_names(name: str | None, product: str | None) -> list[str]:
    result: list[str] = []
    for raw in (product, name):
        value = (raw or "").strip().lower()
        value = PACKAGE_ALIASES.get(value, value)
        if value and value not in result and " " not in value:
            result.append(value)
    return result


class OSVClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._prefetched: dict[PackageIdentity, list[dict[str, Any]]] = {}

    async def _query(
        self, client: httpx.AsyncClient, identity: PackageIdentity
    ) -> list[dict[str, Any]]:
        response = await client.post(
            f"{self.settings.osv_api_url}/query",
            json={
                "version": identity.version,
                "package": {"name": identity.name, "ecosystem": identity.ecosystem},
            },
        )
        response.raise_for_status()
        return response.json().get("vulns", [])

    async def resolve_package(
        self, name: str | None, product: str | None, version: str | None
    ) -> tuple[PackageIdentity | None, str]:
        if self.settings.osv_mode == "disabled" or not version:
            return None, "not_applicable"
        names = package_names(name, product)
        if not names:
            return None, "not_applicable"
        if self.settings.osv_mode == "mock":
            if (names[0], version) in {
                ("axios", "1.11.0"),
                ("axios", "1.18.1"),
                ("react", "19.0.0"),
            }:
                return PackageIdentity("npm", names[0], version), "verified"
            return None, "version_not_found"

        matches: list[PackageIdentity] = []
        timeout = self.settings.osv_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            for package_name in names:
                for ecosystem in ECOSYSTEMS:
                    system = DEPS_SYSTEMS[ecosystem]
                    url = (
                        f"{self.settings.deps_dev_api_url}/systems/{system}/packages/"
                        f"{quote(package_name, safe='')}/versions/{quote(version, safe='')}"
                    )
                    response = await client.get(url)
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    matches.append(PackageIdentity(ecosystem, package_name, version))
                if matches:
                    break
            # Une version retirée ou compromise peut ne plus être exposée par
            # deps.dev alors que les avis OSV la référencent toujours. Dans ce
            # cas, la réponse OSV constitue l'identité de paquet la plus utile.
            if not matches:
                for package_name in names:
                    for ecosystem in ECOSYSTEMS:
                        identity = PackageIdentity(ecosystem, package_name, version)
                        payloads = await self._query(client, identity)
                        if payloads:
                            self._prefetched[identity] = payloads
                            matches.append(identity)
                    if matches:
                        break
        if len(matches) == 1:
            return matches[0], "verified"
        if len(matches) > 1:
            return None, "ambiguous_ecosystem"
        return None, "version_not_found"

    async def vulnerabilities(self, identity: PackageIdentity) -> list[dict[str, Any]]:
        if self.settings.osv_mode == "mock":
            if identity == PackageIdentity("npm", "axios", "1.11.0"):
                return [
                    {
                        "id": "GHSA-test-axios-1110",
                        "aliases": ["CVE-2026-44494"],
                        "summary": "Axios test vulnerability",
                        "details": "Axios 1.11.0 is affected in the OSV test fixture.",
                        "published": "2026-05-29T16:04:00Z",
                        "modified": "2026-06-12T19:30:10Z",
                        "database_specific": {"severity": "HIGH", "cwe_ids": ["CWE-1321"]},
                        "references": [{"type": "ADVISORY", "url": "https://osv.dev/test"}],
                        "affected": [
                            {
                                "package": {"name": "axios", "ecosystem": "npm"},
                                "ranges": [
                                    {
                                        "type": "SEMVER",
                                        "events": [
                                            {"introduced": "1.0.0"},
                                            {"fixed": "1.16.0"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            return []
        if identity in self._prefetched:
            return self._prefetched.pop(identity)
        async with httpx.AsyncClient(timeout=self.settings.osv_timeout_seconds) as client:
            return await self._query(client, identity)
