"""PDF -> Rohtext des Literaturverzeichnisses."""
from __future__ import annotations

import pdfplumber

# Überschriften, ab denen typischerweise das Literaturverzeichnis beginnt.
SECTION_HEADINGS = (
    "literaturverzeichnis",
    "literatur",
    "quellenverzeichnis",
    "references",
    "bibliography",
    "bibliografie",
    "bibliographie",
)

# Überschriften, ab denen das Literaturverzeichnis typischerweise endet.
STOP_HEADINGS = (
    "anhang",
    "appendix",
    "eidesstattliche erklärung",
    "selbstständigkeitserklärung",
    "abbildungsverzeichnis",
)


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

    start_idx = None
    for i, text in enumerate(page_texts):
        first_lines = "\n".join(text.splitlines()[:3]).lower()
        if any(h in first_lines for h in SECTION_HEADINGS):
            start_idx = i
            break

    if start_idx is None:
        # Konnte keine Überschrift finden -> ganzes Dokument zurückgeben,
        # parse_citations.py filtert dann selbst grob.
        return "\n".join(page_texts)

    end_idx = len(page_texts)
    for i in range(start_idx + 1, len(page_texts)):
        first_lines = "\n".join(page_texts[i].splitlines()[:3]).lower()
        if any(h in first_lines for h in STOP_HEADINGS):
            end_idx = i
            break

    return "\n".join(page_texts[start_idx:end_idx])
