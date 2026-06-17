"""PDF -> Rohtext des Literaturverzeichnisses."""
from __future__ import annotations

import re

import pdfplumber

# Überschriften, ab denen typischerweise das Literaturverzeichnis beginnt.
SECTION_HEADINGS = (
    "literaturverzeichnis",
    "literatur",
    "quellenverzeichnis",
    "references",
    "reference list",
    "bibliography",
    "bibliografie",
    "bibliographie",
    "works cited",
)

# Überschriften, ab denen das Literaturverzeichnis typischerweise endet.
STOP_HEADINGS = (
    "anhang",
    "appendix",
    "eidesstattliche erklärung",
    "selbstständigkeitserklärung",
    "abbildungsverzeichnis",
)

# Eine Zeile gilt nur als Kapitelüberschrift, wenn sie - bis auf führende
# Nummerierung ("5", "5.1)", Seitenzahl am Ende und Satzzeichen - exakt einem
# der Heading-Begriffe entspricht. Das verhindert False Positives, wenn das
# Wort "Literatur"/"references" zufällig in einem normalen Fließtext-Satz
# vorkommt (z.B. "...zeigt die Literatur, dass...").
_LEADING_NUMBERING_RE = re.compile(r"^\s*\d+(\.\d+)*[.)]?\s*")
_TRAILING_PAGE_NUM_RE = re.compile(r"[\s.\-–—]*\d{1,4}\s*$")


def _heading_match(line: str, headings: tuple[str, ...]) -> bool:
    candidate = _LEADING_NUMBERING_RE.sub("", line)
    candidate = _TRAILING_PAGE_NUM_RE.sub("", candidate)
    candidate = candidate.strip(" .:-–—").lower()
    return candidate in headings


def _find_heading_line(text: str, headings: tuple[str, ...], max_lines: int = 5) -> bool:
    lines = [l for l in text.splitlines()[:max_lines] if l.strip()]
    return any(_heading_match(line, headings) for line in lines)


def extract_text(pdf_path: str, start_page: int | None = None, end_page: int | None = None) -> str:
    """Extrahiert Rohtext aus dem PDF.

    Wenn start_page/end_page (1-basiert, inklusiv) gesetzt sind, wird nur dieser
    Bereich gelesen. Sonst wird versucht, das Literaturverzeichnis automatisch
    anhand der Kapitelüberschrift zu finden.
    """
    with pdfplumber.open(pdf_path) as pdf:
        if start_page is not None:
            lo = max(start_page - 1, 0)
            hi = end_page if end_page is not None else len(pdf.pages)
            pages = pdf.pages[lo:hi]
            return "\n".join(p.extract_text() or "" for p in pages)
        return _auto_extract_bibliography(pdf)


def _auto_extract_bibliography(pdf) -> str:
    page_texts = [p.extract_text() or "" for p in pdf.pages]

    # Mehrere Treffer sind möglich (z.B. Inhaltsverzeichnis-Eintrag oder pro
    # Kapitel ein eigenes Literaturverzeichnis bei Sammelbänden). Der letzte
    # Treffer vor Dokumentende liegt am wahrscheinlichsten beim tatsächlichen,
    # finalen Literaturverzeichnis einer Abschlussarbeit.
    start_candidates = [
        i for i, text in enumerate(page_texts) if _find_heading_line(text, SECTION_HEADINGS)
    ]

    if not start_candidates:
        # Konnte keine Überschrift finden -> ganzes Dokument zurückgeben,
        # parse_citations.py filtert dann selbst grob.
        return "\n".join(page_texts)

    start_idx = start_candidates[-1]

    end_idx = len(page_texts)
    for i in range(start_idx + 1, len(page_texts)):
        if _find_heading_line(page_texts[i], STOP_HEADINGS) or _find_heading_line(
            page_texts[i], SECTION_HEADINGS
        ):
            end_idx = i
            break

    return "\n".join(page_texts[start_idx:end_idx])
