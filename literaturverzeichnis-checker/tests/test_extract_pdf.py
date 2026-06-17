import src.extract_pdf as extract_pdf
from src.extract_pdf import (
    SECTION_HEADINGS,
    STOP_HEADINGS,
    _auto_extract_bibliography,
    _detect_column_boundary,
    _find_heading_line,
    _heading_match,
    _words_to_text,
)


def _word(text, x0, x1, top):
    return {"text": text, "x0": x0, "x1": x1, "top": top}


def test_heading_match_accepts_plain_heading():
    assert _heading_match("Literaturverzeichnis", SECTION_HEADINGS)
    assert _heading_match("References", SECTION_HEADINGS)


def test_heading_match_accepts_numbered_and_paginated_heading():
    assert _heading_match("5. Literaturverzeichnis", SECTION_HEADINGS)
    assert _heading_match("References 87", SECTION_HEADINGS)
    assert _heading_match("Bibliography ... 120", SECTION_HEADINGS)


def test_heading_match_rejects_word_inside_running_prose():
    sentence = "Wie die bisherige Literatur zeigt, ist dieser Ansatz umstritten."
    assert not _heading_match(sentence, SECTION_HEADINGS)
    sentence_en = "Several references in the literature support this claim."
    assert not _heading_match(sentence_en, SECTION_HEADINGS)


def test_find_heading_line_only_checks_top_lines():
    page_with_prose_heading = (
        "Kapitel 5\n"
        "Diese Seite handelt von einem Thema, das auch in der Literatur diskutiert wird.\n"
        "Mehr Text folgt hier, der nichts mit dem Verzeichnis zu tun hat.\n"
    )
    assert not _find_heading_line(page_with_prose_heading, SECTION_HEADINGS)

    page_with_real_heading = "Literaturverzeichnis\n\nMüller, A. (2020). Titel. Verlag.\n"
    assert _find_heading_line(page_with_real_heading, SECTION_HEADINGS)
    assert not _find_heading_line(page_with_real_heading, STOP_HEADINGS)


def test_detect_column_boundary_finds_gutter_in_two_column_layout():
    words = []
    for row in range(40):
        words.append(_word("left", 50, 100, row * 12))
        words.append(_word("right", 320, 370, row * 12))
    boundary = _detect_column_boundary(words, page_width=595)
    assert boundary is not None
    assert 100 < boundary < 320


def test_detect_column_boundary_returns_none_for_single_column():
    # Fließtext deckt die gesamte Zeilenbreite ab (jede Zeile beginnt an
    # leicht unterschiedlicher Position und reicht über die Seitenmitte
    # hinaus) - es gibt also keine durchgehende Lücke nahe der Mitte.
    words = []
    for row in range(40):
        start = 50 + (row % 5) * 10
        words.append(_word("word", start, start + 480, row * 12))
    assert _detect_column_boundary(words, page_width=595) is None


def test_words_to_text_groups_lines_and_preserves_reading_order():
    words = [
        _word("Second", 60, 120, 12),
        _word("line", 130, 160, 12),
        _word("First", 50, 100, 0),
        _word("line", 110, 140, 0),
    ]
    assert _words_to_text(words) == "First line\nSecond line"


def test_heading_match_accepts_additional_german_and_english_headings():
    assert _heading_match("Literaturliste", SECTION_HEADINGS)
    assert _heading_match("Quellen", SECTION_HEADINGS)
    assert _heading_match("Cited References", SECTION_HEADINGS)
    assert _heading_match("Literature Cited", SECTION_HEADINGS)


def test_detect_column_boundary_finds_gutter_with_few_words_per_column():
    # Eine kurze, zweispaltige Teilseite (z.B. die letzte Seite eines
    # Literaturverzeichnisses) hat oft nur wenige Woerter pro Spalte - die
    # Schwelle muss niedrig genug sein, um das trotzdem als zweispaltig zu
    # erkennen statt page.extract_text() zu verwenden (was Spalten vermischt).
    words = []
    for row in range(10):
        words.append(_word("left", 50, 100, row * 12))
        words.append(_word("right", 320, 370, row * 12))
    boundary = _detect_column_boundary(words, page_width=595)
    assert boundary is not None
    assert 100 < boundary < 320


class _FakePdf:
    def __init__(self, pages):
        self.pages = pages


def test_auto_extract_bibliography_does_not_stop_on_heading_like_line(monkeypatch):
    # Eine Zeile, die zufaellig wie eine Kapitelueberschrift aussieht (z.B.
    # "Quellen" als Stichwort in einer Bildunterschrift), darf das
    # Literaturverzeichnis nicht vorzeitig abschneiden - nur eine echte
    # STOP_HEADINGS-Ueberschrift (z.B. "Anhang") darf das.
    page_texts = [
        "References\n\nMüller, A. (2020). Erste Quelle. Verlag.\n",
        "Smith, J. (2018). Zweite Quelle, siehe auch weitere Quellen dazu.\n",
        "Anhang\n\nWeitere Inhalte, die nicht zum Literaturverzeichnis gehoeren.\n",
    ]
    monkeypatch.setattr(extract_pdf, "_page_text", lambda p: page_texts[p])
    fake_pdf = _FakePdf(pages=list(range(len(page_texts))))
    result = _auto_extract_bibliography(fake_pdf)
    assert "Müller" in result
    assert "Smith" in result
    assert "Weitere Inhalte" not in result


def test_words_to_text_merges_tightly_kerned_doi_fragments():
    # pdfplumber kann ein einzelnes Wort wie "doi.org/10.1016/s0378-5122"
    # bei engem Kerning faelschlich in mehrere "Woerter" mit winzigen
    # Luecken aufspalten - diese muessen wieder zusammengefuehrt werden,
    # waehrend ein echter Wortzwischenraum erhalten bleibt.
    words = [
        _word("https://d", 50, 80, 0),
        _word("oi.o", 80.5, 95, 0),
        _word("rg/10.1016/s0378-5122", 95.4, 160, 0),
        _word("(PubMed)", 165, 200, 0),
    ]
    assert _words_to_text(words) == "https://doi.org/10.1016/s0378-5122 (PubMed)"
