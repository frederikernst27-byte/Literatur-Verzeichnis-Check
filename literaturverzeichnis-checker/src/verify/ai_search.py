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
import re
from dataclasses import dataclass, field

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
class GroundingSource:
    """Eine echte, von der Such-API bestätigte Quelle (z.B. Gemini-Grounding
    oder OpenRouter-`:online`-Annotation) - im Gegensatz zum selbst-berichteten
    'url'-Feld in AIResult, das das Modell frei erfinden (halluzinieren) kann."""
    url: str
    title: str | None = None


@dataclass
class AIResult:
    found: bool
    title: str | None
    authors: str | None
    year: str | None
    url: str | None
    notes: str | None
    grounding_sources: list[GroundingSource] = field(default_factory=list)


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
        message = resp.json()["choices"][0]["message"]
        result = _parse_ai_json(message["content"])
        result.grounding_sources = _extract_openrouter_grounding_sources(message)
        return result


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
        candidate = resp.json()["candidates"][0]
        content = candidate["content"]["parts"][0]["text"]
        result = _parse_ai_json(content)
        result.grounding_sources = _extract_gemini_grounding_sources(candidate)
        return result


_DOI_URL_RE = re.compile(r"doi\.org/(10\.\d{4,9}/[^\s?#]+)", re.IGNORECASE)


def extract_doi_from_url(url: str) -> str | None:
    """Versucht, eine DOI aus einer Grounding-URL zu extrahieren. Deckt
    doi.org-Links direkt ab. Verlagsseiten ohne DOI im URL-Pfad würden einen
    zusätzlichen HTTP-Request zur Seite erfordern - das bleibt bewusst
    außerhalb des Scopes dieser ersten Ausbaustufe."""
    match = _DOI_URL_RE.search(url)
    return match.group(1).rstrip(".,)") if match else None


def _extract_gemini_grounding_sources(candidate: dict) -> list[GroundingSource]:
    """Extrahiert die ECHTEN, von der Google-Suche bestätigten Treffer aus der
    groundingMetadata - im Gegensatz zum 'url'-Feld der vom Modell selbst
    erzeugten JSON-Antwort, das frei erfunden sein kann. Diese Quellen sind
    die Grundlage für die DOI-Bestätigung bzw. die 'Vorschlag, bitte prüfen'-
    Einstufung in classify.py."""
    grounding = candidate.get("groundingMetadata") or {}
    chunks = grounding.get("groundingChunks") or []
    sources = []
    for chunk in chunks:
        web = chunk.get("web") or {}
        uri = web.get("uri")
        if uri:
            sources.append(GroundingSource(url=uri, title=web.get("title")))
    return sources


def _extract_openrouter_grounding_sources(message: dict) -> list[GroundingSource]:
    """Analoges Gegenstück zu _extract_gemini_grounding_sources: OpenRouter-
    `:online`-Modelle liefern echte Quellenangaben als 'annotations' vom Typ
    'url_citation' statt Grounding-Metadaten."""
    sources = []
    for annotation in message.get("annotations") or []:
        if annotation.get("type") != "url_citation":
            continue
        citation = annotation.get("url_citation") or {}
        url = citation.get("url")
        if url:
            sources.append(GroundingSource(url=url, title=citation.get("title")))
    return sources


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
