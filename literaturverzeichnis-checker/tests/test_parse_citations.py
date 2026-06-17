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


def test_does_not_split_running_prose_with_single_year_mention():
    prose = (
        "Dies ist ein langer Fließtext über ein Thema, der zufällig irgendwo mittendrin "
        "eine Klammer mit einer Jahreszahl enthält (Quelle: Müller et al., 2022), aber "
        "ansonsten keine echte Literaturangabe ist."
    )
    citations = parse_citations(prose)
    assert len(citations) == 1


DOI_FRAGMENT_TEXT = """1. Ahlund S, Nordgren B (2013) Is home-based pelvic floor muscle training effective. Acta Obstet Gynecol Scand 92(8):909
10. 1111/aogs.12173
2. Allen RE, Hosker GL (1990) Pelvic floor damage and childbirth. Br J Obstet Gynaecol 97(9):770.
"""


def test_merges_standalone_doi_fragment_into_previous_citation():
    # Eine durch Spalten-/Seitenumbruch verstuemmelte DOI wie "10. 1111/aogs.12173"
    # sieht aus wie ein nummerierter Listeneintrag ("10.") und wuerde sonst als
    # eigenes, bedeutungsloses "Zitat" gezaehlt werden.
    citations = parse_citations(DOI_FRAGMENT_TEXT)
    assert len(citations) == 2
    assert "1111/aogs.12173" in citations[0].raw_text
    assert citations[1].year == "1990"


TRAILING_GARBAGE_TEXT = """[1] Müller, A. (2020). Maschinelles Lernen in der Praxis. Springer, S. 12-34.

[2] Huebner M, DeLancey JOL (2019) Levels of pelvic floor support. Int Urogynecol J 30(9):1593. Archives of Gynecology and Obstetrics (2025) 311:1209-1217
"""


def test_trims_trailing_running_header_from_last_citation():
    citations = parse_citations(TRAILING_GARBAGE_TEXT)
    assert len(citations) == 2
    assert "Archives of Gynecology and Obstetrics" not in citations[1].raw_text
    assert "Levels of pelvic floor support" in citations[1].raw_text


BULLET_TEXT = """• Müller, A. (2020). Maschinelles Lernen in der Praxis. Springer, S. 12-34.

• Smith, J. (2018). Deep Learning for NLP. Journal of AI Research, 45(2), 100-120.
"""


def test_parses_bulleted_entries():
    citations = parse_citations(BULLET_TEXT)
    assert len(citations) == 2
    assert citations[0].year == "2020"
    assert citations[1].year == "2018"


PAREN_NUMBERED_TEXT = """(1) Müller, A. (2020). Maschinelles Lernen in der Praxis. Springer, S. 12-34.

(2) Smith, J. (2018). Deep Learning for NLP. Journal of AI Research, 45(2), 100-120.
"""


def test_parses_parenthesized_numbered_entries():
    citations = parse_citations(PAREN_NUMBERED_TEXT)
    assert len(citations) == 2
    assert citations[0].year == "2020"
    assert citations[1].year == "2018"


VANCOUVER_TEXT = """Mueller A, Schmidt B (2020) Machine learning approaches in practice. Springer J 12:34.

Smith J, Jones K (2018) Deep learning for natural language processing. AI Res 45:100.
"""


def test_parses_vancouver_style_initials_first_authors():
    citations = parse_citations(VANCOUVER_TEXT)
    assert len(citations) == 2
    assert citations[0].year == "2020"
    assert citations[1].year == "2018"


PARTICLE_SURNAME_TEXT = """van der Berg, A. (2020). Eine Untersuchung zu einem Thema. Springer, S. 12-34.

von Neumann, J. (2018). Eine weitere Untersuchung zu einem Thema. Wiley, S. 21-40.
"""


def test_parses_particle_surname_authors():
    citations = parse_citations(PARTICLE_SURNAME_TEXT)
    assert len(citations) == 2
    assert citations[0].year == "2020"
    assert citations[1].year == "2018"


NO_NUMBERING_NO_BLANK_LINES_TEXT = """Müller and Schmidt (2020) wrote about a topic that is described
here in more detail across this line. Springer, S. 1-20.
Smith and Jones (2018) wrote about another topic that is described
here as well across this line. Wiley, S. 21-40.
Weber and Klein (2015) wrote about yet another topic described
here too across this line. Academic, S. 41-60.
"""


def test_splits_entries_without_blank_lines_using_year_boundary_heuristic():
    # Reproduziert den urspruenglichen "1 Zeile in Excel"-Bug: weder
    # Nummerierung noch Autoren-Komma-Muster noch Leerzeilen vorhanden, aber
    # jede Zeile sieht wie ein Autorenanfang aus und der Text davor enthaelt
    # bereits ein Jahr.
    citations = parse_citations(NO_NUMBERING_NO_BLANK_LINES_TEXT)
    assert len(citations) == 3
    assert citations[0].year == "2020"
    assert citations[1].year == "2018"
    assert citations[2].year == "2015"


def test_splits_long_paragraph_with_bare_unparenthesized_years():
    filler = "mit vielen weiteren Worten die hier nur der Mindestlaenge wegen aneinandergereiht werden. " * 3
    text = (
        f"Mueller A. 2020. Erste Quelle zu einem Thema {filler}Verlag, S. 1-20. "
        f"Schmidt B. 2018. Zweite Quelle zu einem anderen Thema {filler}Anderer Verlag, S. 21-40. "
        f"Weber C. 2015. Dritte Quelle zu einem weiteren Thema {filler}Dritter Verlag, S. 41-60."
    )
    assert len(text) > 800
    citations = parse_citations(text)
    assert len(citations) == 3
    assert citations[0].year == "2020"
    assert citations[1].year == "2018"
    assert citations[2].year == "2015"
