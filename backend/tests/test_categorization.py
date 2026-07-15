import asyncio
import json

import httpx

from app.core.config import Settings
from app.services.categorization import ServiceToCategorize, categorize_with_ai


def test_gemini_categorization_uses_structured_output(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            result = {
                "assignments": [
                    {
                        "position": 0,
                        "reuse_category": "__NOUVELLE_CATEGORIE__",
                        "category_name": "Web et API",
                        "confidence": 0.98,
                        "reason": "Apache fournit un serveur HTTP.",
                    }
                ]
            }
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(result)}]}}]}

    class FakeClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args) -> None:  # type: ignore[no-untyped-def]
            return None

        async def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
            captured.update(url=url, headers=headers, body=json)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    settings = Settings(
        app_env="test",
        ai_provider="gemini",
        gemini_api_key="test-key",
        gemini_model="gemini-2.5-flash",
    )
    result = asyncio.run(
        categorize_with_ai(
            [ServiceToCategorize(key="apache", name="Apache", version="2.4")],
            ["Bases de données"],
            settings,
        )
    )

    assert result[0].category_name == "Web et API"
    assert result[0].key == "apache"
    assert captured["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert captured["headers"] == {"x-goog-api-key": "test-key"}
    assert captured["body"]["generationConfig"]["responseMimeType"] == "application/json"
    response_schema = captured["body"]["generationConfig"]["responseSchema"]
    assert "additionalProperties" not in response_schema
    assert "additionalProperties" not in response_schema["properties"]["assignments"]["items"]
    allowed = response_schema["properties"]["assignments"]["items"]["properties"][
        "category_name"
    ]["enum"]
    reuse_choices = response_schema["properties"]["assignments"]["items"]["properties"][
        "reuse_category"
    ]["enum"]
    assert "Bases de données" in allowed
    assert "Frameworks et bibliothèques" in allowed
    assert "Bases de données" in reuse_choices
    assert "__NOUVELLE_CATEGORIE__" in reuse_choices
    prompt = captured["body"]["contents"][0]["parts"][0]["text"]
    assert "plus petit nombre possible" in prompt
    assert "catégorie par produit" in prompt


def test_mock_categorization_groups_related_libraries() -> None:
    settings = Settings(app_env="test", ai_provider="mock")
    result = asyncio.run(
        categorize_with_ai(
            [
                ServiceToCategorize(key="react", name="React"),
                ServiceToCategorize(key="axios", name="Axios"),
                ServiceToCategorize(key="postgres", name="PostgreSQL"),
            ],
            [],
            settings,
        )
    )

    by_key = {item.key: item.category_name for item in result}
    assert by_key["react"] == "Frameworks et bibliothèques"
    assert by_key["axios"] == "Frameworks et bibliothèques"
    assert by_key["postgres"] == "Données et stockage"


def test_mock_categorization_reuses_a_compatible_existing_category() -> None:
    settings = Settings(app_env="test", ai_provider="mock")
    result = asyncio.run(
        categorize_with_ai(
            [
                ServiceToCategorize(key="apache", name="Apache"),
                ServiceToCategorize(key="nginx", name="Nginx"),
            ],
            ["Serveurs web"],
            settings,
        )
    )

    assert {item.category_name for item in result} == {"Serveurs web"}
