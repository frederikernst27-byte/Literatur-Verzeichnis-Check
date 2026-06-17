from src.extract_pdf import SECTION_HEADINGS, STOP_HEADINGS, _find_heading_line, _heading_match


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
