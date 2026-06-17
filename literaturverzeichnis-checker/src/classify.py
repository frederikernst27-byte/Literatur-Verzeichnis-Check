"""Bewertet die Verifikationsergebnisse pro Zitat und vergibt einen Status."""
from __future__ import annotations

from dataclasses import dataclass, field

STATUS_OK = "Gefunden - korrekt"
STATUS_MINOR_ISSUES = "Gefunden - Abweichungen"
STATUS_NOT_FOUND = "Nicht gefunden - vermutlich halluziniert"
STATUS_UNCLEAR = "Unklar - manuelle Pruefung empfohlen"

API_SOURCE_LABELS = {
    "crossref": "CrossRef",
    "openalex": "OpenAlex",
    "semanticscholar": "Semantic Scholar",
}
APIS_CHECKED = "CrossRef, OpenAlex, Semantic Scholar"


@dataclass
class Result:
    number: int
    original_citation: str
    status: str
    found_source: str | None = None
    discrepancies: list[str] = field(default_factory=list)
    method: str = ""
    confidence: float = 0.0
    url: str | None = None


def _make_url(candidate=None, ai_result=None, citation=None) -> str | None:
    """Gibt den besten verfügbaren Link zurück: DOI > direkte URL."""
    # 1. DOI aus API-Kandidat
    if candidate and candidate.doi:
        return f"https://doi.org/{candidate.doi}"
    # 2. URL aus AI-Ergebnis
    if ai_result and ai_result.url:
        return ai_result.url
    # 3. URL direkt aus API-Kandidat
    if candidate and candidate.url:
        return candidate.url
    # 4. DOI aus dem original extrahierten Zitat
    if citation and citation.doi:
        return f"https://doi.org/{citation.doi}"
    return None


def classify(citation, api_match, api_score: float, api_discrepancies: list[str],
             ai_result=None) -> Result:
    """api_match: Candidate|None aus academic_apis.find_best_candidate.
    ai_result: AIResult|None aus ai_search, nur gesetzt wenn KI-Fallback lief.
    """
    if api_match and api_score >= 80:
        api_label = API_SOURCE_LABELS.get(api_match.source_api, api_match.source_api)
        found_source = f"{api_match.title} ({api_match.year or '?'}) [{api_label}]"
        url = _make_url(candidate=api_match, citation=citation)
        if api_discrepancies:
            return Result(
                number=citation.number,
                original_citation=citation.raw_text,
                status=STATUS_MINOR_ISSUES,
                found_source=found_source,
                discrepancies=api_discrepancies,
                method=f"API ({api_label})",
                confidence=api_score,
                url=url,
            )
        return Result(
            number=citation.number,
            original_citation=citation.raw_text,
            status=STATUS_OK,
            found_source=found_source,
            method=f"API ({api_label})",
            confidence=api_score,
            url=url,
        )

    if ai_result is not None:
        if ai_result.found:
            found_source = f"{ai_result.title or '?'} ({ai_result.year or '?'})"
            notes = [ai_result.notes] if ai_result.notes else []
            status = STATUS_MINOR_ISSUES if notes else STATUS_OK
            confidence = 72.0 if notes else 80.0
            return Result(
                number=citation.number,
                original_citation=citation.raw_text,
                status=status,
                found_source=found_source,
                discrepancies=notes,
                method="KI-Websuche (OpenRouter)",
                confidence=confidence,
                url=_make_url(ai_result=ai_result, citation=citation),
            )
        return Result(
            number=citation.number,
            original_citation=citation.raw_text,
            status=STATUS_NOT_FOUND,
            discrepancies=[ai_result.notes] if ai_result.notes else [],
            method="KI-Websuche (OpenRouter)",
            confidence=35.0,
            url=_make_url(citation=citation),
        )

    if api_match and api_score >= 50:
        api_label = API_SOURCE_LABELS.get(api_match.source_api, api_match.source_api)
        return Result(
            number=citation.number,
            original_citation=citation.raw_text,
            status=STATUS_UNCLEAR,
            found_source=f"{api_match.title} ({api_match.year or '?'}) [{api_label}]",
            discrepancies=[f"Nur unsichere Titel-Ähnlichkeit ({api_score:.0f}%) gefunden"],
            method=f"API ({api_label}, schwach)",
            confidence=api_score,
            url=_make_url(candidate=api_match, citation=citation),
        )

    return Result(
        number=citation.number,
        original_citation=citation.raw_text,
        status=STATUS_NOT_FOUND,
        method=f"API ({APIS_CHECKED} geprüft, kein Treffer)",
        confidence=round(api_score, 1) if api_match else 0.0,
        url=_make_url(citation=citation),
    )
