from src.parse_citations import parse_citations

NUMBERED_TEXT = """[1] Müller, A. (2020). Maschinelles Lernen in der Praxis. Springer, S. 12-34.

[2] Smith, J., & Jones, B. (2018). Deep Learning for NLP. Journal of AI Research, 45(2), 100-120.

[3] Erfunden, X. (2099). Eine Quelle, die es nicht gibt. Nirgendwo Verlag.
"""

APA_TEXT = """Müller, A. (2020). Maschinelles Lernen in der Praxis. Springer, S. 12-34.

Smith, J. (2018). Deep Learning for NLP. Journal of AI Research, 45(2), 100-120.
"""


def test_parses_numbered_entries():
    citations = parse_citations(NUMBERED_TEXT)
    assert len(citations) == 3
    assert citations[0].year == "2020"
    assert "Müller" in citations[0].authors
    assert citations[2].year == "2099"


def test_parses_apa_style_entries():
    citations = parse_citations(APA_TEXT)
    assert len(citations) == 2
    assert citations[0].year == "2020"
    assert citations[1].year == "2018"


def test_extracts_pages():
    citations = parse_citations(NUMBERED_TEXT)
    assert citations[0].pages is not None
