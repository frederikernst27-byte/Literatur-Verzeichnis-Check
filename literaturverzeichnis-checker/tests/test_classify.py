from src.classify import (
    STATUS_AI_SUGGESTION,
    STATUS_MINOR_ISSUES,
    STATUS_NOT_FOUND,
    STATUS_OK,
    STATUS_UNCLEAR,
    classify,
)
from src.parse_citations import Citation
from src.verify.academic_apis import Candidate
from src.verify.ai_search import AIResult, GroundingSource


def make_citation(**kwargs):
    defaults = dict(number=1, raw_text="Müller, A. (2020). Titel. Verlag.", authors="Müller, A.", year="2020")
    defaults.update(kwargs)
    return Citation(**defaults)


def test_classify_ok_when_strong_match_no_discrepancies():
    citation = make_citation()
    candidate = Candidate("crossref", "Titel", ["A Müller"], "2020", "10.1/x", "Verlag", "http://x")
    result = classify(citation, candidate, 98, [])
    assert result.status == STATUS_OK


def test_classify_minor_issues_when_discrepancies_present():
    citation = make_citation()
    candidate = Candidate("crossref", "Titel", ["A Müller"], "2020", "10.1/x", "Verlag", "http://x")
    result = classify(citation, candidate, 85, ["Jahr weicht ab: Zitat nennt 2020, gefunden wurde 2021"])
    assert result.status == STATUS_MINOR_ISSUES


def test_classify_not_found_when_no_match_and_no_ai():
    citation = make_citation()
    result = classify(citation, None, 0.0, [])
    assert result.status == STATUS_NOT_FOUND


def test_classify_ai_suggestion_when_ai_found_with_grounding_but_no_doi_confirmation():
    citation = make_citation()
    ai_result = AIResult(
        found=True,
        title="Titel",
        authors="Müller, A.",
        year="2020",
        url="https://example.com/self-reported",
        notes="Sieht passend aus",
        grounding_sources=[GroundingSource(url="https://example.com/real-hit", title="Titel")],
    )
    result = classify(citation, None, 0.0, [], ai_result)
    assert result.status == STATUS_AI_SUGGESTION
    assert "https://example.com/real-hit" in result.found_source


def test_classify_unclear_when_ai_claims_found_but_no_grounding_sources():
    citation = make_citation()
    ai_result = AIResult(
        found=True,
        title="Titel",
        authors="Müller, A.",
        year="2020",
        url="https://example.com/self-reported",
        notes="Behauptet Treffer ohne Beleg",
        grounding_sources=[],
    )
    result = classify(citation, None, 0.0, [], ai_result)
    assert result.status == STATUS_UNCLEAR


def test_classify_not_found_when_ai_reports_not_found():
    citation = make_citation()
    ai_result = AIResult(
        found=False,
        title=None,
        authors=None,
        year=None,
        url=None,
        notes="Keine Quelle gefunden",
        grounding_sources=[],
    )
    result = classify(citation, None, 0.0, [], ai_result)
    assert result.status == STATUS_NOT_FOUND
