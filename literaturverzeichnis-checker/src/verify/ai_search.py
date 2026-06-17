"""Optionaler KI-Fallback mit Websuche, falls die akademischen APIs keinen
sicheren Treffer liefern. Wird nur genutzt, wenn USE_AI=true gesetzt ist.

Unterstützte Provider:
- Gemini (Default): Google AI Studio, Gemini 2.5 Flash mit Search-Grounding.
- OpenRouter: nutzt ein ":online"-Modell (Websuche via OpenRouter).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import requests

TIMEOUT = 45

PROMPT_TEMPLATE = """Du bist ein wissenschaftlicher Literatur-Checker. Prüfe ob die folgende \
Literaturangabe aus einer Abschlussarbeit wirklich existiert. Nutze Google Search zum Nachschlagen.

Literaturangabe: "{citation}"

Wichtige Hinweise:
- Autorenkürzel wie "Schutze S" können Umlaute enthalten (z.B. "Schütze S")
- ±1 Jahr Abweichung ist normal (Online-first vs. Druckausgabe)
- Suche auch nach DOI wenn angegeben

Antworte AUSSCHLIESSLICH als JSON-Objekt mit genau diesen Feldern (kein Text davor oder danach):
{{
  "found": true,
  "title": "exakter Titel der gefundenen Publikation",
  "authors": "Autoren der gefundenen Publikation",
  "year": "Erscheinungsjahr",
  "url": "DOI-Link oder URL zur Quelle",
  "notes": "Abweichungen zur Originalangabe auf Deutsch, oder null wenn alles stimmt"
}}

Falls die Publikation NICHT existiert:
{{
  "found": false,
  "title": null,
  "authors": null,
  "year": null,
  "url": null,
  "notes": "Begründung warum nicht gefunden"
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


def get_ai_provider(name: str, api_key: str | None = None):
    if name == "openrouter":
        return OpenRouterProvider()
    if name == "gemini":
        return GeminiProvider(api_key=api_key)
    raise AIProviderError(f"Unbekannter AI_PROVIDER: {name}")


def _extract_json_from_text(text: str) -> str:
    """Extrahiert JSON-Objekt robust aus KI-Antwort (auch wenn Text drumherum steht)."""
    text = text.strip()
    # Markdown-Codeblöcke entfernen
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    # JSON-Objekt direkt extrahieren falls Prosa davor/danach
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0)
    return text


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
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise AIProviderError("GEMINI_API_KEY fehlt – bitte in den Einstellungen eintragen")

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
    clean = _extract_json_from_text(content)
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        raise AIProviderError(
            f"KI-Antwort konnte nicht als JSON gelesen werden: {e}\nAntwort: {content[:300]}"
        ) from e
    notes = data.get("notes")
    # "null" als String oder leere Notes normalisieren
    if notes in (None, "null", ""):
        notes = None
    return AIResult(
        found=bool(data.get("found")),
        title=data.get("title"),
        authors=data.get("authors"),
        year=str(data.get("year")) if data.get("year") else None,
        url=data.get("url"),
        notes=notes,
    )
