"""Orchestriert: PDF -> Zitate -> Verifikation -> Klassifikation -> Excel.
Wird sowohl von cli.py als auch von email_bot.py genutzt.

Zweiphasige Verarbeitung:
  Phase 1 – API:    Alle Zitate parallel durch CrossRef/OpenAlex/Semantic Scholar.
  Phase 2 – KI:     Unsichere Zitate (Score < 60) sortiert nach Score aufsteigend.
                     Batch 1 (erste 40): Sheet 1 des Excel.
                     Batch 2 (Overflow): zweite KI-Runde → Sheet 2 des Excel.
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
SCORE_THRESHOLD = 60


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
        return [], []

    workers = min(8, len(citations))

    # --- Phase 1: API-Suche für alle Zitate parallel ---
    def api_lookup(citation):
        search_title = citation.title or citation.raw_text
        candidate, score = academic_apis.find_best_candidate(
            search_title, citation.authors, citation.doi
        )
        api_discrepancies = (
            academic_apis.compare_to_citation(citation, candidate, score)
            if candidate and score >= SCORE_THRESHOLD
            else []
        )
        return citation, candidate, score, api_discrepancies

    with ThreadPoolExecutor(max_workers=workers) as executor:
        api_results = list(executor.map(api_lookup, citations))

    # Sicher gefundene Zitate brauchen keine KI
    certain_indices = {
        idx for idx, (_, cand, score, _) in enumerate(api_results)
        if cand and score >= SCORE_THRESHOLD
    }
    uncertain = [
        (idx, cit, cand, score, discrep)
        for idx, (cit, cand, score, discrep) in enumerate(api_results)
        if idx not in certain_indices
    ]
    # Score 0 (kein Treffer) bekommt garantiert KI-Slot (aufsteigend sortiert)
    uncertain.sort(key=lambda x: x[3])

    # Ohne KI: alle direkt klassifizieren
    if not (use_ai and provider):
        return [classify(cit, cand, score, discrep, None) for cit, cand, score, discrep in api_results], []

    batch1 = uncertain[:AI_CALL_LIMIT]
    batch2 = uncertain[AI_CALL_LIMIT:]  # Overflow → zweites Sheet

    def run_ai_batch(batch):
        results: dict[int, object] = {}

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

        with ThreadPoolExecutor(max_workers=workers) as executor:
            for future in as_completed(executor.submit(ai_lookup, item) for item in batch):
                idx, result = future.result()
                results[idx] = result
        return results

    # Batch 1 KI
    ai_results1 = run_ai_batch(batch1)

    # Sheet 1: alle Zitate (certain + batch1 mit KI, overflow ohne KI)
    sheet1: dict[int, object] = {}
    for idx, (cit, cand, score, discrep) in enumerate(api_results):
        if idx in certain_indices:
            sheet1[idx] = classify(cit, cand, score, discrep, None)
        elif idx in ai_results1:
            sheet1[idx] = ai_results1[idx]
        else:
            sheet1[idx] = classify(cit, cand, score, discrep, None)

    results_sheet1 = [sheet1[i] for i in range(len(citations))]

    if not batch2:
        return results_sheet1, []

    # Batch 2 KI für Overflow
    ai_results2 = run_ai_batch(batch2)
    results_sheet2 = [ai_results2[idx] for idx, *_ in batch2]

    return results_sheet1, results_sheet2


def run_pipeline_to_excel(pdf_path: str, output_path: str, **kwargs) -> str:
    sheet1, sheet2 = run_pipeline(pdf_path, **kwargs)
    export_to_excel(sheet1, sheet2, output_path)
    return output_path


def has_server_ai_key() -> bool:
    """Prüft ob ein KI-Key auf dem Server konfiguriert ist (OpenRouter oder Gemini)."""
    return bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY"))
