from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.vulnerability import NVDCache

MOCK_CPES = {
    "nginx": [{"cpeName": "cpe:2.3:a:f5:nginx:*:*:*:*:*:*:*:*", "titles": [{"title": "F5 NGINX"}]}],
    "postgresql": [
        {
            "cpeName": "cpe:2.3:a:postgresql:postgresql:*:*:*:*:*:*:*:*",
            "titles": [{"title": "PostgreSQL"}],
        }
    ],
    "react": [
        {
            "cpeName": "cpe:2.3:a:facebook:react:19.0.0:*:*:*:*:*:*:*",
            "titles": [{"title": "Facebook React 19.0.0"}],
        }
    ],
    "icehrm": [
        {
            "cpeName": "cpe:2.3:a:icehrm:icehrm:31.0.0.os:*:*:*:*:*:*:*",
            "titles": [{"title": "IceHRM 31.0.0.OS"}],
        }
    ],
}
MOCK_CVES = {
    "f5:nginx": [
        {
            "cve": {
                "id": "CVE-2021-23017",
                "published": "2021-06-01T13:15:07.000",
                "lastModified": "2024-11-21T05:49:39.327",
                "vulnStatus": "Analyzed",
                "descriptions": [
                    {
                        "lang": "en",
                        "value": (
                            "A resolver vulnerability in NGINX may allow a forged UDP "
                            "packet to cause memory corruption."
                        ),
                    }
                ],
                "metrics": {
                    "cvssMetricV31": [
                        {"cvssData": {"version": "3.1", "baseScore": 7.7, "baseSeverity": "HIGH"}}
                    ]
                },
                "weaknesses": [{"description": [{"lang": "en", "value": "CWE-787"}]}],
                "references": [{"url": "https://nvd.nist.gov/vuln/detail/CVE-2021-23017"}],
                "configurations": [
                    {
                        "nodes": [
                            {
                                "cpeMatch": [
                                    {
                                        "vulnerable": True,
                                        "criteria": "cpe:2.3:a:f5:nginx:*:*:*:*:*:*:*:*",
                                        "versionEndExcluding": "1.21.0",
                                    }
                                ]
                            }
                        ]
                    }
                ],
            }
        }
    ],
    "postgresql:postgresql": [
        {
            "cve": {
                "id": "CVE-2024-10979",
                "published": "2024-11-14T13:15:03.820",
                "lastModified": "2025-01-10T16:15:28.150",
                "vulnStatus": "Analyzed",
                "descriptions": [
                    {
                        "lang": "en",
                        "value": (
                            "PostgreSQL PL/Perl environment variable manipulation vulnerability."
                        ),
                    }
                ],
                "metrics": {
                    "cvssMetricV31": [
                        {"cvssData": {"version": "3.1", "baseScore": 8.8, "baseSeverity": "HIGH"}}
                    ]
                },
                "weaknesses": [],
                "references": [{"url": "https://nvd.nist.gov/vuln/detail/CVE-2024-10979"}],
                "configurations": [
                    {
                        "nodes": [
                            {
                                "cpeMatch": [
                                    {
                                        "vulnerable": True,
                                        "criteria": (
                                            "cpe:2.3:a:postgresql:postgresql:*:*:*:*:*:*:*:*"
                                        ),
                                        "versionStartIncluding": "12.0",
                                        "versionEndExcluding": "12.20",
                                    }
                                ]
                            }
                        ]
                    }
                ],
            }
        }
    ],
    "facebook:react": [
        {
            "cve": {
                "id": "CVE-2025-55182",
                "published": "2025-12-03T15:15:49.103",
                "lastModified": "2026-06-17T17:16:21.633",
                "vulnStatus": "Analyzed",
                "descriptions": [
                    {
                        "lang": "en",
                        "value": "React Server Components remote code execution vulnerability.",
                    }
                ],
                "metrics": {
                    "cvssMetricV31": [
                        {
                            "cvssData": {
                                "version": "3.1",
                                "baseScore": 10.0,
                                "baseSeverity": "CRITICAL",
                            }
                        }
                    ]
                },
                "weaknesses": [{"description": [{"lang": "en", "value": "CWE-502"}]}],
                "references": [{"url": "https://nvd.nist.gov/vuln/detail/CVE-2025-55182"}],
                "configurations": [
                    {
                        "nodes": [
                            {
                                "cpeMatch": [
                                    {
                                        "vulnerable": True,
                                        "criteria": "cpe:2.3:a:facebook:react:19.0.0:*:*:*:*:*:*:*",
                                    }
                                ]
                            }
                        ]
                    }
                ],
            }
        }
    ],
}

MOCK_KEYWORD_CVES = {
    "icehrm": [
        {
            "cve": {
                "id": "CVE-2026-15478",
                "published": "2026-01-01T00:00:00.000",
                "lastModified": "2026-07-12T04:30:07.683",
                "vulnStatus": "Awaiting Analysis",
                "descriptions": [
                    {
                        "lang": "en",
                        "value": "IceHRM up to 35.0.1 is affected by SQL injection.",
                    }
                ],
                "metrics": {},
                "weaknesses": [],
                "references": [],
                "configurations": [],
            }
        }
    ]
}

MOCK_CVE_RECORDS = {
    "CVE-2026-15478": {
        "containers": {
            "cna": {
                "affected": [
                    {
                        "vendor": "n/a",
                        "product": "IceHRM",
                        "versions": [
                            {"version": "35.0.0", "status": "affected"},
                            {"version": "35.0.1", "status": "affected"},
                        ],
                        "cpes": ["cpe:2.3:a:icehrm:icehrm:*:*:*:*:*:*:*:*"],
                    }
                ],
                "metrics": [
                    {
                        "cvssV3_1": {
                            "version": "3.1",
                            "baseScore": 6.3,
                            "baseSeverity": "MEDIUM",
                        }
                    }
                ],
            }
        }
    }
}


class NVDClient:
    def __init__(self, settings: Settings, db: AsyncSession):
        self.settings = settings
        self.db = db

    async def _cached(self, cache_type: str, key: str) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        item = await self.db.scalar(
            select(NVDCache).where(NVDCache.cache_type == cache_type, NVDCache.cache_key == key)
        )
        return (
            item.payload
            if item and item.expires_at.replace(tzinfo=item.expires_at.tzinfo or UTC) > now
            else None
        )

    async def _store(
        self, cache_type: str, key: str, payload: dict[str, Any], etag: str | None = None
    ) -> None:
        now = datetime.now(UTC)
        item = await self.db.scalar(
            select(NVDCache).where(NVDCache.cache_type == cache_type, NVDCache.cache_key == key)
        )
        if item is None:
            item = NVDCache(cache_type=cache_type, cache_key=key, payload=payload, expires_at=now)
            self.db.add(item)
        item.payload, item.etag, item.fetched_at = payload, etag, now
        item.expires_at = now + timedelta(seconds=self.settings.nvd_cache_ttl_seconds)

    async def _request(self, url: str, params: dict[str, Any], cache_type: str) -> dict[str, Any]:
        key = f"{url}?" + "&".join(f"{k}={quote(str(v))}" for k, v in sorted(params.items()))
        if cached := await self._cached(cache_type, key):
            return cached
        headers = {"User-Agent": "MICEPP-Tracker/0.1"}
        if self.settings.nvd_api_key:
            headers["apiKey"] = self.settings.nvd_api_key
        async with httpx.AsyncClient(
            timeout=self.settings.nvd_timeout_seconds, headers=headers
        ) as client:
            for attempt in range(4):
                response = await client.get(url, params=params)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                    payload = response.json()
                    await self._store(cache_type, key, payload, response.headers.get("etag"))
                    return payload
                retry_after = response.headers.get("retry-after")
                await asyncio.sleep(
                    float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                )
        raise RuntimeError("NVD temporairement indisponible après plusieurs tentatives")

    async def search_cpes(self, keyword: str) -> list[dict[str, Any]]:
        if self.settings.nvd_mode == "disabled":
            return []
        if self.settings.nvd_mode == "mock":
            lowered = keyword.lower()
            return next((items for name, items in MOCK_CPES.items() if name in lowered), [])
        result: list[dict[str, Any]] = []
        start = 0
        for _ in range(self.settings.nvd_max_pages):
            payload = await self._request(
                self.settings.nvd_cpe_url, {"keywordSearch": keyword, "startIndex": start}, "cpe"
            )
            result.extend(item.get("cpe", {}) for item in payload.get("products", []))
            per_page, total = payload.get("resultsPerPage", 0), payload.get("totalResults", 0)
            if not per_page or start + per_page >= total:
                break
            start += per_page
        return result

    async def cpe_exists(self, cpe_uri: str) -> bool:
        if self.settings.nvd_mode == "disabled":
            raise RuntimeError("La vérification CPE NVD est désactivée.")
        if self.settings.nvd_mode == "mock":
            return any(
                item.get("cpeName") == cpe_uri
                for items in MOCK_CPES.values()
                for item in items
            )
        payload = await self._request(
            self.settings.nvd_cpe_url,
            {"cpeMatchString": cpe_uri},
            "cpe_exact",
        )
        return any(
            item.get("cpe", {}).get("cpeName") == cpe_uri
            and item.get("cpe", {}).get("deprecated") is not True
            for item in payload.get("products", [])
        )

    async def cves_for_cpe(self, cpe_uri: str) -> list[dict[str, Any]]:
        if self.settings.nvd_mode == "disabled":
            return []
        if self.settings.nvd_mode == "mock":
            parts = cpe_uri.split(":")
            return MOCK_CVES.get(f"{parts[3]}:{parts[4]}", [])
        result: list[dict[str, Any]] = []
        start = 0
        for _ in range(self.settings.nvd_max_pages):
            payload = await self._request(
                self.settings.nvd_cve_url,
                {"cpeName": cpe_uri, "isVulnerable": "", "startIndex": start},
                "cve",
            )
            result.extend(payload.get("vulnerabilities", []))
            per_page, total = payload.get("resultsPerPage", 0), payload.get("totalResults", 0)
            if not per_page or start + per_page >= total:
                break
            start += per_page
        return result

    async def cves_for_keyword(self, keyword: str) -> list[dict[str, Any]]:
        if self.settings.nvd_mode == "disabled":
            return []
        if self.settings.nvd_mode == "mock":
            lowered = keyword.lower()
            return next((items for name, items in MOCK_KEYWORD_CVES.items() if name in lowered), [])
        result: list[dict[str, Any]] = []
        start = 0
        for _ in range(self.settings.nvd_max_pages):
            payload = await self._request(
                self.settings.nvd_cve_url,
                {"keywordSearch": keyword, "startIndex": start},
                "cve_keyword",
            )
            result.extend(payload.get("vulnerabilities", []))
            per_page, total = payload.get("resultsPerPage", 0), payload.get("totalResults", 0)
            if not per_page or start + per_page >= total:
                break
            start += per_page
        return result

    async def cve_record(self, cve_id: str) -> dict[str, Any] | None:
        if self.settings.nvd_mode == "disabled":
            return None
        if self.settings.nvd_mode == "mock":
            return MOCK_CVE_RECORDS.get(cve_id)
        try:
            return await self._request(
                f"{self.settings.cve_api_url.rstrip('/')}/{quote(cve_id, safe='')}",
                {},
                "cve_record",
            )
        except Exception:
            # La NVD reste exploitable si CVE.org est momentanément indisponible.
            return None
