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


def _detect_column_boundary(words: list[dict], page_width: float) -> float | None:
    """Sucht eine vertikale Lücke (Gutter) nahe der Seitenmitte, die auf ein
    zweispaltiges Layout hindeutet. Gibt None zurück, wenn die Seite
    einspaltig ist (kein klarer Gutter vorhanden)."""
    if not words:
        return None
    candidates = range(int(page_width * 0.35), int(page_width * 0.65), 5)
    best_x, best_overlap = None, None
    for x in candidates:
        overlap = sum(1 for w in words if w["x0"] < x < w["x1"])
        if best_overlap is None or overlap < best_overlap:
            best_overlap, best_x = overlap, x
    if best_overlap is None or best_overlap > max(2, len(words) * 0.02):
        return None
    left = sum(1 for w in words if w["x1"] <= best_x)
    right = sum(1 for w in words if w["x0"] >= best_x)
    if left > 20 and right > 20:
        return best_x
    return None


def _words_to_text(words: list[dict], line_tolerance: float = 3) -> str:
    if not words:
        return ""
    words = sorted(words, key=lambda w: (round(w["top"] / line_tolerance), w["x0"]))
    lines: list[str] = []
    current: list[dict] = []
    bucket = None
    for w in words:
        b = round(w["top"] / line_tolerance)
        if bucket is None or b == bucket:
            current.append(w)
            bucket = b
        else:
            lines.append(" ".join(x["text"] for x in current))
            current, bucket = [w], b
    if current:
        lines.append(" ".join(x["text"] for x in current))
    return "\n".join(lines)


def _page_text(page) -> str:
    """Extrahiert Seitentext spaltenbewusst.

    pdfplumbers Standard-`extract_text()` sortiert Wörter primär nach
    vertikaler Position und reiht bei zweispaltigem Layout (z.B. Fachartikel)
    Wörter aus linker und rechter Spalte, die zufällig auf derselben Höhe
    stehen, in einer Zeile aneinander - das zerstört insbesondere
    Literaturlisten in der zweiten Spalte. Wird ein klarer Spalten-Gutter
    erkannt, wird stattdessen erst die linke, dann die rechte Spalte
    extrahiert.
    """
    words = page.extract_words()
    boundary = _detect_column_boundary(words, page.width)
    if boundary is None:
        return page.extract_text() or ""
    left = [w for w in words if w["x0"] < boundary]
    right = [w for w in words if w["x0"] >= boundary]
    return _words_to_text(left) + "\n" + _words_to_text(right)


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
            return "\n".join(_page_text(p) for p in pages)
        return _auto_extract_bibliography(pdf)


def _auto_extract_bibliography(pdf) -> str:
    page_texts = [_page_text(p) for p in pdf.pages]

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
