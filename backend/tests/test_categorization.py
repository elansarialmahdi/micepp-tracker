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
                        "category_name": "Serveurs web",
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

    assert result[0].category_name == "Serveurs web"
    assert result[0].key == "apache"
    assert captured["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert captured["headers"] == {"x-goog-api-key": "test-key"}
    assert captured["body"]["generationConfig"]["responseMimeType"] == "application/json"
    response_schema = captured["body"]["generationConfig"]["responseSchema"]
    assert "additionalProperties" not in response_schema
    assert "additionalProperties" not in response_schema["properties"]["assignments"]["items"]
