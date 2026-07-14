from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings

logger = logging.getLogger("micepp.categorization")


class CategorizationUnavailable(RuntimeError):
    pass


class CategorizationFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class ServiceToCategorize:
    key: str
    name: str
    version: str | None = None
    vendor: str | None = None
    product: str | None = None


@dataclass(frozen=True)
class CategoryAssignment:
    key: str
    category_name: str
    confidence: float
    reason: str


class _GeminiAssignment(BaseModel):
    position: int = Field(ge=0)
    category_name: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)


class _GeminiResponse(BaseModel):
    assignments: list[_GeminiAssignment]


def categorization_available(provider: str | None, gemini_api_key: str | None = None) -> bool:
    return provider == "mock" or (provider == "gemini" and bool(gemini_api_key))


def categorize_services(names: list[str], provider: str | None) -> dict[str, str]:
    """Deterministic compatibility provider used by existing tests and imports."""
    if provider != "mock":
        return {}
    categories: dict[str, str] = {}
    for name in names:
        lowered = name.casefold()
        if any(token in lowered for token in ("nginx", "apache", "iis", "http")):
            categories[name] = "Web"
        elif any(token in lowered for token in ("postgres", "mysql", "mongo", "redis")):
            categories[name] = "Données"
        elif any(token in lowered for token in ("ssh", "openssh", "vpn")):
            categories[name] = "Accès distant"
        else:
            categories[name] = "Autres"
    return categories


def _mock_assignments(items: list[ServiceToCategorize]) -> list[CategoryAssignment]:
    def category_for(name: str) -> str:
        lowered = name.casefold()
        if any(token in lowered for token in ("nginx", "apache", "iis", "http")):
            return "Serveurs web"
        if any(token in lowered for token in ("php", "python", "node", "java", "ruby")):
            return "Langages et runtimes"
        if any(token in lowered for token in ("postgres", "mysql", "mongo", "redis")):
            return "Bases de données"
        if any(token in lowered for token in ("ssh", "openssh", "vpn")):
            return "Accès distant"
        return "Logiciels divers"

    return [
        CategoryAssignment(
            key=item.key,
            category_name=category_for(item.name),
            confidence=0.9,
            reason="Classification déterministe du provider de test.",
        )
        for item in items
    ]


async def categorize_with_ai(
    items: list[ServiceToCategorize],
    existing_categories: list[str],
    settings: Settings,
) -> list[CategoryAssignment]:
    if settings.ai_provider == "mock":
        return _mock_assignments(items)
    if settings.ai_provider != "gemini" or not settings.gemini_api_key:
        raise CategorizationUnavailable(
            "Gemini n’est pas configuré. Ajoutez GEMINI_API_KEY et AI_PROVIDER=gemini."
        )

    payload_items = [
        {
            "position": position,
            "name": item.name,
            "version": item.version,
            "vendor": item.vendor,
            "product": item.product,
        }
        for position, item in enumerate(items)
    ]
    prompt = (
        "Tu classes des logiciels et services techniques dans un inventaire de cybersécurité. "
        "Pour chaque élément, choisis exactement une catégorie française concise et réutilisable. "
        "Réutilise à l’identique une catégorie existante lorsqu’elle convient. "
        "Si aucune ne convient, "
        "propose une nouvelle catégorie métier précise; n’utilise jamais une catégorie vague comme "
        "'Autres'. Apache, Nginx et IIS sont des serveurs web; PHP, Python, "
        "Node.js et Java sont des langages ou runtimes. Ne modifie pas les positions "
        "et retourne chaque position une seule fois.\n\n"
        f"Catégories existantes: {json.dumps(existing_categories, ensure_ascii=False)}\n"
        f"Éléments: {json.dumps(payload_items, ensure_ascii=False)}"
    )
    schema = {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "position": {"type": "integer"},
                        "category_name": {
                            "type": "string",
                            "description": "Catégorie française concise, existante ou nouvelle.",
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string"},
                    },
                    "required": ["position", "category_name", "confidence", "reason"],
                },
            }
        },
        "required": ["assignments"],
    }
    url = f"{settings.gemini_api_url.rstrip('/')}/models/{settings.gemini_model}:generateContent"
    try:
        async with httpx.AsyncClient(timeout=settings.gemini_timeout_seconds) as client:
            response = await client.post(
                url,
                headers={"x-goog-api-key": settings.gemini_api_key},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "responseMimeType": "application/json",
                        "responseSchema": schema,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _GeminiResponse.model_validate_json(text)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "gemini_categorization_http_error",
            extra={
                "status_code": exc.response.status_code,
                "response_excerpt": exc.response.text[:1000],
                "model": settings.gemini_model,
            },
        )
        raise CategorizationFailed(
            "Gemini a refusé la demande de catégorisation. Réessayez dans quelques instants."
        ) from exc
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
        logger.warning(
            "gemini_categorization_invalid_response",
            extra={"error_type": type(exc).__name__, "model": settings.gemini_model},
        )
        raise CategorizationFailed(
            "Gemini n’a pas pu catégoriser les services. Réessayez dans quelques instants."
        ) from exc

    by_position = {assignment.position: assignment for assignment in parsed.assignments}
    if set(by_position) != set(range(len(items))):
        raise CategorizationFailed("La réponse de Gemini est incomplète.")
    return [
        CategoryAssignment(
            key=item.key,
            category_name=" ".join(by_position[position].category_name.split())[:200],
            confidence=by_position[position].confidence,
            reason=by_position[position].reason,
        )
        for position, item in enumerate(items)
    ]
