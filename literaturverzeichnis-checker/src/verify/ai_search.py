"""KI-Fallback mit Websuche und direktem Datenbankzugriff (CrossRef/OpenAlex/Semantic Scholar).
Wird genutzt wenn USE_AI=true gesetzt ist.

Unterstützte Provider:
- OpenRouter (Default): nutzt google/gemini-2.5-flash:online (Websuche via OpenRouter).
- Gemini: Google AI Studio, Gemini 2.5 Flash mit Search-Grounding.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .academic_apis import Candidate

TIMEOUT = 45

PROMPT_TEMPLATE = """Du prüfst, ob die folgende Literaturangabe aus einer Abschlussarbeit \
wirklich existiert.

Literaturangabe: "{citation}"

Wir haben bereits die akademischen Datenbanken CrossRef, OpenAlex und Semantic Scholar \
durchsucht. Hier sind die gefundenen Kandidaten (können leer sein):

{api_candidates_block}

Bitte tue Folgendes:
1. Prüfe, ob einer der oben gelisteten Datenbankeinträge zur Literaturangabe passt \
(trotz möglicher Abweichungen durch OCR-Fehler, Sonderzeichen oder Abkürzungen).
2. Falls keiner passt: Suche im Web nach der Literaturangabe um zu prüfen, ob sie existiert.
3. Gib an, welche Abweichungen es gibt (z. B. falsches Jahr, falsch geschriebene Autoren, \
andere Seitenangaben, gekürzter Titel im PDF).

Antworte AUSSCHLIESSLICH als JSON-Objekt mit genau diesen Feldern:
{{
  "found": true/false,
  "title": "gefundener Titel oder null",
  "authors": "gefundene Autoren oder null",
  "year": "gefundenes Jahr oder null",
  "url": "Link zur Quelle oder null",
  "notes": "kurze Begründung / Abweichungen zur Originalangabe, auf Deutsch"
}}"""


def _format_api_candidates(candidates) -> str:
    if not candidates:
        return "(Keine Kandidaten in den Datenbanken gefunden)"
    lines = []
    for i, c in enumerate(candidates, 1):
        authors = ", ".join(c.authors[:3]) if c.authors else "unbekannt"
        if len(c.authors) > 3:
            authors += " et al."
        lines.append(
            f"{i}. [{c.source_api}] \"{c.title}\" – {authors} ({c.year or '?'}) "
            f"| Zeitschrift: {c.venue or 'unbekannt'} | DOI: {c.doi or 'kein'}"
        )
    return "\n".join(lines)


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
        self.model = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
        if not self.api_key:
            raise AIProviderError("OPENROUTER_API_KEY fehlt in der .env")

    def search_citation(self, citation_text: str, api_candidates=None) -> AIResult:
        # Füge :online hinzu damit OpenRouter Websuche aktiviert
        model = self.model if self.model.endswith(":online") else f"{self.model}:online"
        candidates_block = _format_api_candidates(api_candidates or [])
        prompt = PROMPT_TEMPLATE.format(
            citation=citation_text,
            api_candidates_block=candidates_block,
        )
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
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

    def search_citation(self, citation_text: str, api_candidates=None) -> AIResult:
        candidates_block = _format_api_candidates(api_candidates or [])
        prompt = PROMPT_TEMPLATE.format(
            citation=citation_text,
            api_candidates_block=candidates_block,
        )
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": self.api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
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
