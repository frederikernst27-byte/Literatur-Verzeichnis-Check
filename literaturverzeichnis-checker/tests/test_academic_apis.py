from src.parse_citations import Citation
from src.verify.academic_apis import Candidate, compare_to_citation, re_split_authors


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
