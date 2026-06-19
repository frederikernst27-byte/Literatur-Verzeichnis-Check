"""Orchestriert: PDF -> Zitate -> Verifikation -> Klassifikation -> Excel.
Wird sowohl von cli.py als auch von email_bot.py genutzt.

Zweiphasige Verarbeitung:
  Phase 1 – API:    Alle Zitate parallel durch CrossRef/OpenAlex/Semantic Scholar.
  Phase 2 – KI:     Alle unsicheren Zitate (Score < SCORE_THRESHOLD) erhalten
                     KI-Behandlung. Kein Limit – alle Ergebnisse in Sheet 1.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .classify import classify
from .export_excel import export_to_excel
from .extract_pdf import extract_text
from .parse_citations import parse_citations
from .verify import academic_apis
from .verify.ai_search import AIProviderError, get_ai_provider

SCORE_THRESHOLD = 60

# Häufige OCR-Artefakte die API-Suche sabotieren
_OCR_FIXES = [
    (re.compile(r"^\*e\b"),          "The "),   # "*e role" → "The role"
    (re.compile(r"^:e\b"),           "The "),   # ":e role" → "The role"
    (re.compile(r"\*e\b"),           "The "),
    (re.compile(r":e\b"),            "The "),
    (re.compile(r"\bu¨\b", re.I),    "ü"),
    (re.compile(r"\bo¨\b", re.I),    "ö"),
    (re.compile(r"\ba¨\b", re.I),    "ä"),
]


def _clean_ocr(text: str) -> str:
    for pattern, replacement in _OCR_FIXES:
        text = pattern.sub(replacement, text)
    # Leerzeichen in zusammengezogene Wörter einfügen ist zu fehleranfällig;
    # stattdessen nur sichtbare Trennzeichen normalisieren
    return text.strip()


def run_pipeline(
    pdf_path: str,
    start_page: int | None = None,
    end_page: int | None = None,
    use_ai: bool | None = None,
    ai_provider: str | None = None,
    openrouter_api_key: str | None = None,
    gemini_api_key: str | None = None,  # legacy, wird ignoriert
):
    use_ai = use_ai if use_ai is not None else os.environ.get("USE_AI", "false").lower() == "true"
    ai_provider_name = ai_provider or os.environ.get("AI_PROVIDER", "openrouter")

    provider = None
    if use_ai:
        try:
            provider = get_ai_provider(ai_provider_name, api_key=openrouter_api_key)
        except AIProviderError as e:
            raise AIProviderError(
                f"KI-Fallback ist aktiviert, kann aber nicht initialisiert werden: {e}"
            ) from e

    text = extract_text(pdf_path, start_page, end_page)
    citations = parse_citations(text)

    # Wenn der regelbasierte Parser versagt (z.B. Springer-Buchkapitel ohne
    # erkennbare Überschrift), nutze die KI um die Referenzen direkt aus dem
    # Rohtext zu extrahieren.
    if len(citations) < 2 and provider:
        try:
            raw_strings = provider.extract_citations_from_text(text)
            if len(raw_strings) > len(citations):
                from .parse_citations import _parse_entry
                citations = [_parse_entry(i + 1, s) for i, s in enumerate(raw_strings)]
        except Exception:
            pass

    if not citations:
        return [], []

    workers = min(8, len(citations))

    # --- Phase 1: API-Suche für alle Zitate parallel ---
    def api_lookup(citation):
        raw = _clean_ocr(citation.title or citation.raw_text)
        candidate, score = academic_apis.find_best_candidate(
            raw, citation.authors, citation.doi
        )
        api_discrepancies = (
            academic_apis.compare_to_citation(citation, candidate, score)
            if candidate and score >= SCORE_THRESHOLD
            else []
        )
        return citation, candidate, score, api_discrepancies

    with ThreadPoolExecutor(max_workers=workers) as executor:
        api_results = list(executor.map(api_lookup, citations))

    # Ohne KI: alle direkt klassifizieren
    if not (use_ai and provider):
        return [classify(cit, cand, score, discrep, None) for cit, cand, score, discrep in api_results], []

    certain_indices = {
        idx for idx, (_, cand, score, _) in enumerate(api_results)
        if cand and score >= SCORE_THRESHOLD
    }
    uncertain = [
        (idx, cit, cand, score, discrep)
        for idx, (cit, cand, score, discrep) in enumerate(api_results)
        if idx not in certain_indices
    ]
    uncertain.sort(key=lambda x: x[3])  # Score aufsteigend (0 zuerst)

    # --- Phase 2: KI für ALLE unsicheren Zitate (kein Limit) ---
    ai_results: dict[int, object] = {}

    def ai_lookup(item):
        idx, citation, candidate, score, api_discrepancies = item
        raw = _clean_ocr(citation.title or citation.raw_text)
        try:
            all_candidates = academic_apis.get_all_candidates(raw)
            web_search = len(all_candidates) == 0
            ai_result = provider.search_citation(
                _clean_ocr(citation.raw_text),
                api_candidates=all_candidates,
                web_search=web_search,
            )
        except Exception:
            ai_result = None
        return idx, classify(citation, candidate, score, api_discrepancies, ai_result)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for future in as_completed(executor.submit(ai_lookup, item) for item in uncertain):
            idx, result = future.result()
            ai_results[idx] = result

    results = []
    for idx, (cit, cand, score, discrep) in enumerate(api_results):
        if idx in certain_indices:
            results.append(classify(cit, cand, score, discrep, None))
        else:
            results.append(ai_results.get(idx, classify(cit, cand, score, discrep, None)))

    return results, []


def run_pipeline_to_excel(pdf_path: str, output_path: str, **kwargs) -> str:
    sheet1, sheet2 = run_pipeline(pdf_path, **kwargs)
    export_to_excel(sheet1, sheet2, output_path)
    return output_path


def has_server_ai_key() -> bool:
    """Prüft ob ein KI-Key auf dem Server konfiguriert ist (OpenRouter oder Gemini)."""
    return bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY"))
