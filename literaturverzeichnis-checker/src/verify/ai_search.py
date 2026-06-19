"""KI-Fallback mit Websuche und direktem Datenbankzugriff (CrossRef/OpenAlex/Semantic Scholar).
Wird genutzt wenn USE_AI=true gesetzt ist.

Unterstützte Provider:
- OpenRouter (Default): nutzt google/gemini-2.5-flash:online (Websuche via OpenRouter).
- Gemini: Google AI Studio, Gemini 2.5 Flash mit Search-Grounding.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .academic_apis import Candidate

TIMEOUT = 25

EXTRACT_PROMPT = """Der folgende Text wurde per OCR aus einer wissenschaftlichen PDF-Datei extrahiert. \
Er enthält ein Literaturverzeichnis, möglicherweise aber auch Fließtext oder Kopfzeilen.

Extrahiere NUR die einzelnen Literaturangaben als Liste. Ignoriere Fließtext, Kapitelüberschriften, \
Seitenzahlen und Kopfzeilen. Jede Literaturangabe soll vollständig und in einer Zeile stehen.

Antworte AUSSCHLIESSLICH als JSON-Array von Strings, z.B.:
["Costello, T. (2012). RACI – Getting projects unstuck. IT Professional, 14(2), 64–63.",
 "Dumas, M., La Rosa, M., Mendling, J., & Reijers, H. A. (2018). Fundamentals of business process management. Springer."]

Text:
\"\"\"
{raw_text}
\"\"\"
"""

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


def get_ai_provider(name: str, api_key: str | None = None):
    if name == "openrouter":
        return OpenRouterProvider(api_key=api_key)
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
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.model = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
        if not self.api_key:
            raise AIProviderError("OPENROUTER_API_KEY fehlt – bitte in den Einstellungen eintragen")

    def extract_citations_from_text(self, raw_text: str) -> list[str]:
        prompt = EXTRACT_PROMPT.format(raw_text=raw_text[:12000])
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model.removesuffix(":online"),
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return _parse_citation_list(content)

    def search_citation(self, citation_text: str, api_candidates=None, web_search: bool = True) -> AIResult:
        base = self.model.removesuffix(":online")
        model = f"{base}:online" if web_search else base
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
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        if not content:
            raise AIProviderError(f"OpenRouter lieferte leere Antwort: {str(data)[:300]}")
        return _parse_ai_json(content)


class GeminiProvider:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise AIProviderError("GEMINI_API_KEY fehlt – bitte in den Einstellungen eintragen")

    def extract_citations_from_text(self, raw_text: str) -> list[str]:
        prompt = EXTRACT_PROMPT.format(raw_text=raw_text[:12000])
        body: dict = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": self.api_key},
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        candidate = (data.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        content = next((p["text"] for p in parts if "text" in p), "")
        return _parse_citation_list(content)

    def search_citation(self, citation_text: str, api_candidates=None, web_search: bool = True) -> AIResult:
        candidates_block = _format_api_candidates(api_candidates or [])
        prompt = PROMPT_TEMPLATE.format(
            citation=citation_text,
            api_candidates_block=candidates_block,
        )
        body: dict = {"contents": [{"parts": [{"text": prompt}]}]}
        if web_search:
            body["tools"] = [{"google_search": {}}]
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": self.api_key},
            json=body,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        candidate = (data.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        # Bei aktivierter Websuche können mehrere Parts zurückkommen; wir nehmen den ersten mit Text
        text_content = next((p["text"] for p in parts if "text" in p), None)
        if not text_content:
            finish = candidate.get("finishReason", "UNKNOWN")
            raise AIProviderError(f"Gemini lieferte keinen Text (finishReason={finish}): {str(data)[:300]}")
        return _parse_ai_json(text_content)


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


def _parse_citation_list(content: str) -> list[str]:
    """Parst eine JSON-Array-Antwort der KI in eine Liste von Zitat-Strings."""
    clean = _extract_json_from_text(content)
    # Manchmal antwortet die KI mit einem Objekt {"references": [...]}
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        # Fallback: Zeilen als einzelne Einträge
        return [l.strip().strip('",') for l in content.splitlines() if len(l.strip()) > 20]
    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()]
    if isinstance(data, dict):
        for key in ("references", "citations", "list", "items"):
            if isinstance(data.get(key), list):
                return [str(x).strip() for x in data[key] if str(x).strip()]
    return []
