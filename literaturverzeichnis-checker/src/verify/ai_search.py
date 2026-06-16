"""Optionaler KI-Fallback mit Websuche, falls die akademischen APIs keinen
sicheren Treffer liefern. Wird nur genutzt, wenn USE_AI=true gesetzt ist.

Unterstützte Provider:
- OpenRouter (Default): nutzt ein ":online"-Modell (Websuche via OpenRouter),
  aktuell z.B. ein kostenloses Modell konfigurierbar über OPENROUTER_MODEL.
- Gemini: Google AI Studio, Gemini 2.5 Flash mit Search-Grounding.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import requests

TIMEOUT = 30

PROMPT_TEMPLATE = """Du prüfst, ob die folgende Literaturangabe aus einer Abschlussarbeit \
wirklich existiert. Suche im Web danach.

Literaturangabe: "{citation}"

Antworte AUSSCHLIESSLICH als JSON-Objekt mit genau diesen Feldern:
{{
  "found": true/false,
  "title": "gefundener Titel oder null",
  "authors": "gefundene Autoren oder null",
  "year": "gefundenes Jahr oder null",
  "url": "Link zur Quelle oder null",
  "notes": "kurze Begründung / Abweichungen zur Originalangabe, auf Deutsch"
}}"""


@dataclass
class AIResult:
    found: bool
    title: str | None
    authors: str | None
    year: str | None
    url: str | None
    notes: str | None


class AIProviderError(RuntimeError):
    pass


def get_ai_provider(name: str):
    if name == "openrouter":
        return OpenRouterProvider()
    if name == "gemini":
        return GeminiProvider()
    raise AIProviderError(f"Unbekannter AI_PROVIDER: {name}")


class OpenRouterProvider:
    def __init__(self):
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self.model = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        if not self.api_key:
            raise AIProviderError("OPENROUTER_API_KEY fehlt in der .env")

    def search_citation(self, citation_text: str) -> AIResult:
        model = self.model if self.model.endswith(":online") else f"{self.model}:online"
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": PROMPT_TEMPLATE.format(citation=citation_text)}],
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_ai_json(content)


class GeminiProvider:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise AIProviderError("GEMINI_API_KEY fehlt in der .env")

    def search_citation(self, citation_text: str) -> AIResult:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": self.api_key},
            json={
                "contents": [{"parts": [{"text": PROMPT_TEMPLATE.format(citation=citation_text)}]}],
                "tools": [{"google_search": {}}],
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_ai_json(content)


def _parse_ai_json(content: str) -> AIResult:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content.split("\n", 1)[1] if "\n" in content else content
        if content.lower().startswith("json"):
            content = content[4:]
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise AIProviderError(f"KI-Antwort konnte nicht als JSON gelesen werden: {e}") from e
    return AIResult(
        found=bool(data.get("found")),
        title=data.get("title"),
        authors=data.get("authors"),
        year=str(data.get("year")) if data.get("year") else None,
        url=data.get("url"),
        notes=data.get("notes"),
    )
