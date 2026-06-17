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


def test_splits_long_paragraph_with_multiple_years_into_entries():
    filler = "mit vielen weiteren Worten die hier nur der Mindestlaenge wegen aneinandergereiht werden. " * 3
    text = (
        f"Müller, A. (2020). Erste Quelle zu einem Thema {filler}Verlag, S. 1-20. "
        f"Schmidt, B. (2018). Zweite Quelle zu einem anderen Thema {filler}Anderer Verlag, S. 21-40. "
        f"Weber, C. (2015). Dritte Quelle zu einem weiteren Thema {filler}Dritter Verlag, S. 41-60."
    )
    assert len(text) > 800
    citations = parse_citations(text)
    assert len(citations) == 3
    assert citations[0].year == "2020"
    assert citations[1].year == "2018"
    assert citations[2].year == "2015"


def test_doi_fragment_merged_into_preceding_entry():
    # Simulates a page-number line like "915. https://doi.org/..." being treated
    # as a numbered entry and then merged back into the preceding citation.
    text = (
        "1. Ahlund S (2013) Is pelvic floor training effective. Acta Obstet 92(8):909–\n"
        "915. https://doi.org/10.1111/aogs.12173\n"
        "2. Smith J (2019) Another study. Some Journal 5(1):1–10.\n"
    )
    citations = parse_citations(text)
    assert len(citations) == 2
    assert "doi.org" in citations[0].raw_text


def test_authors_and_affiliations_stripped():
    text = (
        "1. Alewijnse D (2001) Pelvic floor re-education. BJU Int 88:887–893. "
        "https://doi.org/10.1046/j.1464-410X.2001.02427.x (PubMed PMID: 11851626)\n"
        "Authors and Affiliations\n"
        "Institute of Gynecology, University Hospital, Berlin, Germany\n"
        "2. Beer M (2025) Effect of postpartum pessary. Arch Gynecol Obstet 311:1209.\n"
    )
    citations = parse_citations(text)
    assert len(citations) == 2
    assert "Authors and Affiliations" not in citations[0].raw_text


def test_publishers_note_stripped():
    text = (
        "1. Elenskaia K (2011) The greatest risk for prolapse. Int Urogynecol J 22(10):1207. "
        "https://doi.org/10.1007/s00192-011-1501-5\n"
        "Publisher's Note Springer Nature remains neutral with regard to jurisdictional claims.\n"
    )
    citations = parse_citations(text)
    assert len(citations) == 1
    assert "Publisher" not in citations[0].raw_text


def test_does_not_split_running_prose_with_single_year_mention():
    prose = (
        "Dies ist ein langer Fließtext über ein Thema, der zufällig irgendwo mittendrin "
        "eine Klammer mit einer Jahreszahl enthält (Quelle: Müller et al., 2022), aber "
        "ansonsten keine echte Literaturangabe ist."
    )
    citations = parse_citations(prose)
    assert len(citations) == 1
