"""Orchestriert: PDF -> Zitate -> Verifikation -> Klassifikation -> Excel.
Wird sowohl von cli.py als auch von email_bot.py genutzt.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from .classify import classify
from .export_excel import export_to_excel
from .extract_pdf import extract_text
from .parse_citations import parse_citations
from .verify import academic_apis
from .verify.ai_search import AIProviderError, get_ai_provider


def run_pipeline(
    pdf_path: str,
    start_page: int | None = None,
    end_page: int | None = None,
    use_ai: bool | None = None,
    ai_provider: str | None = None,
):
    use_ai = use_ai if use_ai is not None else os.environ.get("USE_AI", "false").lower() == "true"
    ai_provider_name = ai_provider or os.environ.get("AI_PROVIDER", "openrouter")

    provider = None
    if use_ai:
        try:
            provider = get_ai_provider(ai_provider_name)
        except AIProviderError as e:
            raise AIProviderError(
                f"KI-Fallback ist aktiviert (USE_AI=true), kann aber nicht initialisiert werden: {e}"
            ) from e

    text = extract_text(pdf_path, start_page, end_page)
    citations = parse_citations(text)

    def verify_one(citation):
        candidate, score = academic_apis.find_best_candidate(
            citation.title or citation.raw_text, citation.authors
        )
        api_discrepancies = (
            academic_apis.compare_to_citation(citation, candidate, score)
            if candidate and score >= 80
            else []
        )

        ai_result = None
        if use_ai and provider and (not candidate or score < 80):
            ai_result = provider.search_citation(citation.raw_text)

        return classify(citation, candidate, score, api_discrepancies, ai_result)

    if not citations:
        return []

    with ThreadPoolExecutor(max_workers=min(8, len(citations))) as executor:
        return list(executor.map(verify_one, citations))


def run_pipeline_to_excel(pdf_path: str, output_path: str, **kwargs) -> str:
    results = run_pipeline(pdf_path, **kwargs)
    export_to_excel(results, output_path)
    return output_path
