from __future__ import annotations

import asyncio
import json
import logging
import unicodedata
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings

logger = logging.getLogger("micepp.categorization")

BROAD_CATEGORY_TAXONOMY = (
    "Web et API",
    "Frameworks et bibliothèques",
    "Langages et runtimes",
    "Données et stockage",
    "Systèmes et infrastructure",
    "Sécurité et accès",
    "Observabilité et opérations",
    "Outils de développement",
)
NEW_CATEGORY_SENTINEL = "__NOUVELLE_CATEGORIE__"


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
    reuse_category: str = Field(min_length=1, max_length=200)
    category_name: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)


class _GeminiResponse(BaseModel):
    assignments: list[_GeminiAssignment]


def _gemini_http_error_message(response: httpx.Response) -> str:
    """Turn Gemini client errors into actionable messages without exposing secrets."""
    status_code = response.status_code
    if status_code == 401:
        return (
            "La clé Gemini est invalide, ou le compte de service qui lui est lié est "
            "désactivé ou supprimé. Vérifiez cette clé dans Google AI Studio."
        )
    if status_code == 403:
        return (
            "La clé Gemini n’a pas l’autorisation d’utiliser l’API. Vérifiez ses restrictions "
            "et l’accès du projet dans Google AI Studio."
        )
    if status_code == 429:
        return "Le quota Gemini est épuisé. Vérifiez le quota ou la facturation du projet."
    if status_code == 404:
        try:
            provider_message = str(response.json().get("error", {}).get("message", ""))
        except (TypeError, ValueError):
            provider_message = ""
        if "no longer available to new users" in provider_message.casefold():
            return (
                "Le modèle Gemini configuré n’est plus accessible aux nouveaux utilisateurs. "
                "Utilisez un modèle récent, par exemple gemini-3.5-flash-lite."
            )
        return "Le modèle Gemini configuré est introuvable ou indisponible pour ce projet."
    if status_code == 400:
        return "Gemini a refusé le format de la demande de catégorisation."
    return "Gemini est temporairement indisponible. Réessayez dans quelques instants."


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


def _category_family(value: str) -> str | None:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    families = (
        ("frameworks", ("framework", "bibliothe", "library", "frontend", "backend")),
        ("web", ("web", "api", "http", "reverse proxy", "proxy")),
        ("runtimes", ("langage", "runtime", "execution")),
        ("data", ("donnee", "database", "base de", "stockage")),
        ("security", ("securite", "acces", "auth", "identite")),
        ("observability", ("observabilite", "monitoring", "operation", "journal")),
        ("development", ("developpement", "devops", "build", "outils")),
        ("systems", ("systeme", "infrastructure", "reseau", "serveur")),
    )
    return next(
        (family for family, markers in families if any(marker in normalized for marker in markers)),
        None,
    )


def _reuse_compatible_category(
    suggested: str, existing_categories: list[str]
) -> str | None:
    suggested_key = suggested.strip().casefold()
    exact = next(
        (
            category
            for category in existing_categories
            if category.strip().casefold() == suggested_key
        ),
        None,
    )
    if exact:
        return exact
    family = _category_family(suggested)
    if family is None:
        return None
    return next(
        (category for category in existing_categories if _category_family(category) == family),
        None,
    )


def _mock_assignments(
    items: list[ServiceToCategorize], existing_categories: list[str]
) -> list[CategoryAssignment]:
    def category_for(name: str) -> str:
        lowered = name.casefold()
        if any(token in lowered for token in ("nginx", "apache", "iis", "http", "traefik")):
            return "Web et API"
        if any(
            token in lowered
            for token in ("react", "angular", "vue", "axios", "express", "django", "spring")
        ):
            return "Frameworks et bibliothèques"
        if any(token in lowered for token in ("php", "python", "node", "java", "ruby")):
            return "Langages et runtimes"
        if any(token in lowered for token in ("postgres", "mysql", "mongo", "redis")):
            return "Données et stockage"
        if any(token in lowered for token in ("ssh", "openssh", "vpn")):
            return "Sécurité et accès"
        return "Systèmes et infrastructure"

    assignments: list[CategoryAssignment] = []
    for item in items:
        suggested = category_for(item.name)
        assignments.append(
            CategoryAssignment(
                key=item.key,
                category_name=(
                    _reuse_compatible_category(suggested, existing_categories) or suggested
                ),
                confidence=0.9,
                reason="Classification déterministe du provider de test.",
            )
        )
    return assignments


async def categorize_with_ai(
    items: list[ServiceToCategorize],
    existing_categories: list[str],
    settings: Settings,
) -> list[CategoryAssignment]:
    if settings.ai_provider == "mock":
        return _mock_assignments(items, existing_categories)
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
    allowed_categories = list(
        dict.fromkeys([*existing_categories, *BROAD_CATEGORY_TAXONOMY])
    )
    target_category_count = max(
        1, min(len(items), max(2, min(6, (len(items) + 3) // 4)))
    )
    prompt = (
        "Tu classes des logiciels et services techniques dans un inventaire de cybersécurité. "
        "Analyse tout le lot avant de répondre et regroupe les éléments dans le plus petit nombre "
        "possible de familles fonctionnelles larges. Ne crée jamais une catégorie par produit, "
        "éditeur ou service. Des technologies seulement voisines doivent partager une catégorie. "
        f"Pour ce lot, vise au maximum {target_category_count} catégories distinctes, "
        "sauf nécessité "
        "technique évidente. Pour chaque élément, examine d'abord toutes les catégories "
        "existantes. "
        "Dans reuse_category, choisis obligatoirement le libellé exact d'une catégorie existante "
        "dès qu'elle est fonctionnellement compatible, même si son nom diffère de la taxonomie. "
        f"Utilise {NEW_CATEGORY_SENTINEL!r} uniquement si aucune catégorie existante ne convient. "
        "Dans category_name, indique alors la famille large à créer. Apache, Nginx et les reverse "
        "proxies relèvent de 'Web et API'; React, Axios et les "
        "frameworks relèvent de 'Frameworks et bibliothèques'. Ne modifie pas les positions et "
        "retourne chaque position une seule fois.\n\n"
        f"Catégories existantes: {json.dumps(existing_categories, ensure_ascii=False)}\n"
        f"Catégories autorisées: {json.dumps(allowed_categories, ensure_ascii=False)}\n"
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
                        "reuse_category": {
                            "type": "string",
                            "enum": [*existing_categories, NEW_CATEGORY_SENTINEL],
                            "description": (
                                "Catégorie existante exacte à réutiliser, ou sentinelle seulement "
                                "si aucune catégorie existante n'est compatible."
                            ),
                        },
                        "category_name": {
                            "type": "string",
                            "enum": allowed_categories,
                            "description": "Catégorie fonctionnelle large choisie dans la liste.",
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "position",
                        "reuse_category",
                        "category_name",
                        "confidence",
                        "reason",
                    ],
                },
            }
        },
        "required": ["assignments"],
    }
    url = f"{settings.gemini_api_url.rstrip('/')}/models/{settings.gemini_model}:generateContent"
    try:
        async with httpx.AsyncClient(timeout=settings.gemini_timeout_seconds) as client:
            for attempt in range(3):
                response = await client.post(
                    url,
                    headers={"x-goog-api-key": settings.gemini_api_key},
                    json={
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.1,
                            "thinkingConfig": {"thinkingLevel": "minimal"},
                            "responseMimeType": "application/json",
                            "responseSchema": schema,
                        },
                    },
                )
                if response.status_code not in {429, 503} or attempt == 2:
                    response.raise_for_status()
                    break
                await asyncio.sleep(2**attempt)
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
        raise CategorizationFailed(_gemini_http_error_message(exc.response)) from exc
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
    if any(
        assignment.category_name not in allowed_categories
        for assignment in parsed.assignments
    ):
        raise CategorizationFailed("Gemini a retourné une catégorie non autorisée.")
    reuse_choices = {*existing_categories, NEW_CATEGORY_SENTINEL}
    if any(assignment.reuse_category not in reuse_choices for assignment in parsed.assignments):
        raise CategorizationFailed("Gemini a retourné une catégorie existante non autorisée.")
    return [
        CategoryAssignment(
            key=item.key,
            category_name=" ".join(
                (
                    by_position[position].category_name
                    if by_position[position].reuse_category == NEW_CATEGORY_SENTINEL
                    else by_position[position].reuse_category
                ).split()
            )[:200],
            confidence=by_position[position].confidence,
            reason=by_position[position].reason,
        )
        for position, item in enumerate(items)
    ]
