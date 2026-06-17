from src.classify import STATUS_MINOR_ISSUES, STATUS_NOT_FOUND, STATUS_OK, classify
from src.parse_citations import Citation
from src.verify.academic_apis import Candidate


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


def test_classify_url_from_doi():
    citation = make_citation()
    candidate = Candidate("crossref", "Titel", ["A Müller"], "2020", "10.1234/xyz", "Verlag", None)
    result = classify(citation, candidate, 95, [])
    assert result.url == "https://doi.org/10.1234/xyz"


def test_classify_url_from_citation_doi_when_no_candidate():
    citation = make_citation(doi="10.9999/abc")
    result = classify(citation, None, 0.0, [])
    assert result.url == "https://doi.org/10.9999/abc"
