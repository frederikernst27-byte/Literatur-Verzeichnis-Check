from unittest.mock import patch

from src.parse_citations import Citation
from src.verify.academic_apis import (
    Candidate,
    compare_to_citation,
    find_best_candidate,
    re_split_authors,
)


def test_re_split_authors_handles_ampersand_and_comma():
    assert re_split_authors("Müller, A. & Schmidt, B.") == ["Müller, A", "Schmidt, B"]


def test_compare_to_citation_flags_year_mismatch():
    citation = Citation(number=1, raw_text="x", authors="Müller, A.", year="2020")
    candidate = Candidate("crossref", "Titel", ["A Müller"], "2021", None, None, None)
    discrepancies = compare_to_citation(citation, candidate, 100.0)
    assert any("Jahr" in d for d in discrepancies)


def test_compare_to_citation_flags_unmatched_author():
    citation = Citation(number=1, raw_text="x", authors="Komplett, Anders", year="2020")
    candidate = Candidate("crossref", "Titel", ["A Müller"], "2020", None, None, None)
    discrepancies = compare_to_citation(citation, candidate, 100.0)
    assert any("Autor" in d for d in discrepancies)


def test_find_best_candidate_uses_exact_doi_lookup_when_available():
    doi_candidate = Candidate("crossref", "Echter Titel", ["A Müller"], "2020", "10.1/x", None, None)
    with patch(
        "src.verify.academic_apis.query_crossref_by_doi", return_value=doi_candidate
    ) as mocked_doi, patch(
        "src.verify.academic_apis.query_crossref"
    ) as mocked_search:
        candidate, score = find_best_candidate("Irgendein Titel", doi="10.1/x")
    assert candidate is doi_candidate
    assert score == 100.0
    mocked_doi.assert_called_once_with("10.1/x")
    mocked_search.assert_not_called()


def test_find_best_candidate_falls_back_to_fuzzy_search_if_doi_lookup_fails():
    with patch("src.verify.academic_apis.query_crossref_by_doi", return_value=None), patch(
        "src.verify.academic_apis.query_crossref", return_value=[]
    ), patch("src.verify.academic_apis.query_openalex", return_value=[]), patch(
        "src.verify.academic_apis.query_semantic_scholar", return_value=[]
    ):
        candidate, score = find_best_candidate("Ein Titel der nicht gefunden wird", doi="10.1/missing")
    assert candidate is None
    assert score == 0.0
