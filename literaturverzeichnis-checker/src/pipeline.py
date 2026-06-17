"""Orchestriert: PDF -> Zitate -> Verifikation -> Klassifikation -> Excel.
Wird sowohl von cli.py als auch von email_bot.py genutzt.

Zweiphasige Verarbeitung:
  Phase 1 – API: Alle Zitate parallel durch CrossRef/OpenAlex/Semantic Scholar.
  Phase 2 – KI:  Unsichere Zitate (Score < 80) sortiert nach Score aufsteigend
                  (schlechteste zuerst), bis zu AI_CALL_LIMIT KI-Calls parallel.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from .classify import classify
from .export_excel import export_to_excel
from .extract_pdf import extract_text
from .parse_citations import parse_citations
from .verify import academic_apis
from .verify.ai_search import AIProviderError, get_ai_provider

AI_CALL_LIMIT = 40


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

    if not citations:
        return []

    # --- Phase 1: API-Suche für alle Zitate parallel ---
    def api_lookup(citation):
        search_title = citation.title or citation.raw_text
        candidate, score = academic_apis.find_best_candidate(
            search_title, citation.authors, citation.doi
        )
        api_discrepancies = (
            academic_apis.compare_to_citation(citation, candidate, score)
            if candidate and score >= 80
            else []
        )
        return citation, candidate, score, api_discrepancies

    workers = min(8, len(citations))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        api_results = list(executor.map(api_lookup, citations))

    # --- Phase 2: KI für unsichere Zitate, sortiert nach Score (schlechteste zuerst) ---
    if not (use_ai and provider):
        return [classify(cit, cand, score, discrep, None) for cit, cand, score, discrep in api_results]

    # Index beibehalten für Reihenfolge im Excel
    uncertain = [
        (idx, cit, cand, score, discrep)
        for idx, (cit, cand, score, discrep) in enumerate(api_results)
        if not cand or score < 80
    ]
    # Score 0 (kein Treffer) zuerst → bekommt garantiert KI-Slot
    uncertain.sort(key=lambda x: x[3])

    ai_slots = uncertain[:AI_CALL_LIMIT]
    no_ai_slots = uncertain[AI_CALL_LIMIT:]

    def ai_lookup(item):
        idx, citation, candidate, score, api_discrepancies = item
        search_title = citation.title or citation.raw_text
        try:
            all_candidates = academic_apis.get_all_candidates(search_title)
            web_search = len(all_candidates) == 0
            ai_result = provider.search_citation(
                citation.raw_text, api_candidates=all_candidates, web_search=web_search
            )
        except Exception:
            ai_result = None
        return idx, classify(citation, candidate, score, api_discrepancies, ai_result)

    results: dict[int, object] = {}

    # Certain citations brauchen keine KI
    for idx, (cit, cand, score, discrep) in enumerate(api_results):
        if cand and score >= 80:
            results[idx] = classify(cit, cand, score, discrep, None)

    # Übrig gebliebene uncertain ohne KI-Slot direkt klassifizieren
    for idx, cit, cand, score, discrep in no_ai_slots:
        results[idx] = classify(cit, cand, score, discrep, None)

    # KI-Slots parallel verarbeiten
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(ai_lookup, item): item for item in ai_slots}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    return [results[i] for i in range(len(citations))]


def run_pipeline_to_excel(pdf_path: str, output_path: str, **kwargs) -> str:
    results = run_pipeline(pdf_path, **kwargs)
    export_to_excel(results, output_path)
    return output_path


def has_server_ai_key() -> bool:
    """Prüft ob ein KI-Key auf dem Server konfiguriert ist (OpenRouter oder Gemini)."""
    return bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY"))
