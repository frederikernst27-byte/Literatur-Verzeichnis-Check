"""Rohtext des Literaturverzeichnisses -> Liste einzelner Zitate mit Metadaten.

Die Heuristiken decken die gängigsten Stile ab (nummeriert, APA-artig mit
hängendem Einzug). Sie sind bewusst einfach gehalten - Ziel ist eine
brauchbare Grundlage für die anschließende Verifikation, kein
hundertprozentig korrekter Zitations-Parser.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NUMBERED_LINE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s+")
YEAR_RE = re.compile(r"\(?\b(1[89]\d{2}|20\d{2})[a-z]?\b\)?")
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,;]+)", re.IGNORECASE)
PAGES_RE = re.compile(r"\b[Ss]\.?\s*(\d+)\s*(?:[-–—]\s*(\d+))?\b|\bpp?\.\s*(\d+)\s*(?:[-–—]\s*(\d+))?")
AUTHOR_START_RE = re.compile(r"^[A-ZÄÖÜ][\wÀ-ÿ'\-]+,\s*[A-ZÄÖÜ]")

# Ein "Eintrag", der nach dem Splitten nur aus einem DOI-/URL-Rest besteht,
# ist keine eigene Quelle - er wurde vermutlich durch einen Spalten- oder
# Seitenumbruch von der eigentlichen Quellenangabe losgerissen. Erkennbar
# u.a. daran, dass er kein Leerzeichen enthält (echte Zitate enthalten immer
# Autorennamen mit Leerzeichen), aber Ziffern und Schrägstrich/Punkt (DOI-
# bzw. URL-typisch). Greift auch, wenn ein numerischer DOI-Anfang wie
# "10. 1111/aogs.12173" fälschlich als nummerierter Listeneintrag erkannt
# und das "10." dabei als Nummerierung abgeschnitten wurde (übrig bleibt
# z.B. "1111/aogs.12173").
_ORPHAN_FRAGMENT_RE = re.compile(r"^(?:https?://)?[\w.\-/():]+$")

# Laufende Kopfzeilen (Zeitschriftenname + Jahrgang/Seiten) oder
# "Authors and Affiliations"/"Publisher's Note"-Blöcke, die beim Seitenumbruch
# an die letzte Quellenangabe einer Seite angehängt werden.
_TRAILING_GARBAGE_RE = re.compile(
    r"[A-ZÄÖÜ][\w &\-]+\s\(20\d{2}\)\s*\d+:\d+[\-–]\d+"
    r"|Authors? and Affiliations\b"
    r"|Publisher'?s Note\b",
    re.IGNORECASE,
)


@dataclass
class Citation:
    number: int
    raw_text: str
    authors: str | None = None
    year: str | None = None
    title: str | None = None
    pages: str | None = None
    doi: str | None = None
    discrepancies: list[str] = field(default_factory=list)


def parse_citations(text: str) -> list[Citation]:
    entries = _split_entries(text)
    return [_parse_entry(i + 1, entry) for i, entry in enumerate(entries)]


def _split_entries(text: str) -> list[str]:
    lines = [l for l in text.splitlines()]
    # Kopfzeilen wie "Literaturverzeichnis" / Seitenzahlen-Zeilen rauswerfen
    lines = [l for l in lines if l.strip() and not re.fullmatch(r"\d+", l.strip())]

    numbered_indices = [i for i, l in enumerate(lines) if NUMBERED_LINE.match(l)]
    if len(numbered_indices) >= 2:
        return _postprocess_entries(_split_by_indices(lines, numbered_indices))

    author_indices = [i for i, l in enumerate(lines) if AUTHOR_START_RE.match(l)]
    if len(author_indices) >= 2:
        return _postprocess_entries(_split_by_indices(lines, author_indices))

    # Fallback: durch Leerzeilen getrennte Absätze
    paragraphs, current = [], []
    for l in lines:
        if not l.strip():
            if current:
                paragraphs.append(" ".join(current))
                current = []
        else:
            current.append(l.strip())
    if current:
        paragraphs.append(" ".join(current))
    paragraphs = [p for p in paragraphs if len(p) > 20]

    # Falls ein "Absatz" ungewöhnlich lang ist (deutlich länger als ein
    # einzelnes Literaturzitat), handelt es sich vermutlich um Fließtext statt
    # einer echten Quellenangabe (z.B. wenn keine Leerzeilen erkannt wurden).
    # Letzter Versuch: anhand wiederkehrender Jahreszahlen-in-Klammern
    # nachträglich in einzelne Einträge aufteilen.
    result = []
    for p in paragraphs:
        result.extend(_split_long_paragraph(p) if len(p) > 800 else [p])
    return _postprocess_entries(result)


def _postprocess_entries(entries: list[str]) -> list[str]:
    """Räumt typische Artefakte von Seiten-/Spaltenumbrüchen auf: ein
    abgerissenes DOI/URL-Fragment wird zur vorherigen Quelle gehängt statt
    als eigener (bedeutungsloser) Eintrag stehen zu bleiben, und laufende
    Kopfzeilen/'Authors and Affiliations'-Blöcke werden vom Ende des letzten
    Eintrags abgeschnitten."""
    merged: list[str] = []
    for entry in entries:
        stripped = entry.strip()
        if merged and _is_orphan_fragment(stripped):
            merged[-1] = f"{merged[-1]} {stripped}"
        else:
            merged.append(entry)

    if merged:
        garbage_match = _TRAILING_GARBAGE_RE.search(merged[-1])
        if garbage_match:
            merged[-1] = merged[-1][: garbage_match.start()].strip()

    return merged


def _is_orphan_fragment(entry: str) -> bool:
    """True, wenn `entry` kein eigenständiges Zitat ist, sondern nur ein
    losgerissenes DOI-/URL-Fragment (kein Leerzeichen, kein Jahr, kein
    Autorenanfang, aber Ziffern + Punkt/Schrägstrich-typisch für DOIs)."""
    if not entry or " " in entry or len(entry) > 60:
        return False
    if YEAR_RE.search(entry) or AUTHOR_START_RE.match(entry):
        return False
    return bool(re.search(r"\d", entry)) and bool(re.search(r"[./]", entry)) and bool(
        _ORPHAN_FRAGMENT_RE.match(entry)
    )


def _split_long_paragraph(paragraph: str) -> list[str]:
    year_starts = [m.start() for m in re.finditer(r"(?<![\d(])\(?(1[89]\d{2}|20\d{2})[a-z]?\)", paragraph)]
    if len(year_starts) < 2:
        return [paragraph]

    # Vor jedem Jahr suchen wir den Beginn des vermutlichen Autorennamens
    # (Großbuchstabe nach Satzende), um den Eintrag dort zu beginnen.
    boundaries = [0]
    for pos in year_starts[1:]:
        search_start = max(boundaries[-1], pos - 120)
        prefix = paragraph[search_start:pos]
        match = list(re.finditer(r"(?:^|[.!?]\s+)([A-ZÄÖÜ])", prefix))
        boundary = search_start + match[-1].start(1) if match else pos
        if boundary > boundaries[-1]:
            boundaries.append(boundary)

    boundaries.append(len(paragraph))
    entries = [paragraph[s:e].strip() for s, e in zip(boundaries, boundaries[1:])]
    return [e for e in entries if len(e) > 20]


_NUMBERED_PREFIX_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")


def _split_by_indices(lines: list[str], indices: list[int]) -> list[str]:
    raw_chunks = [
        " ".join(l.strip() for l in lines[start:end])
        for start, end in zip(indices, indices[1:] + [len(lines)])
    ]

    entries: list[str] = []
    for chunk in raw_chunks:
        # Ein verstümmeltes DOI wie "10. 1111/aogs.12173" sieht aus wie ein
        # nummerierter Listeneintrag ("10."). Bevor die vermeintliche
        # Nummerierung abgeschnitten wird, prüfen wir, ob Nummer+Rest ohne
        # das künstliche Leerzeichen ein DOI-/URL-Fragment ergeben - falls ja,
        # gehört das Fragment (mit erhaltenem "10.") zum vorherigen Eintrag.
        prefix_match = _NUMBERED_PREFIX_RE.match(chunk)
        if entries and prefix_match:
            rejoined = f"{prefix_match.group(1)}.{prefix_match.group(2)}"
            if _is_orphan_fragment(rejoined):
                entries[-1] = f"{entries[-1]} {rejoined}"
                continue

        entries.append(NUMBERED_LINE.sub("", chunk, count=1).strip())
    return entries


def _parse_entry(number: int, raw: str) -> Citation:
    citation = Citation(number=number, raw_text=raw)

    year_match = YEAR_RE.search(raw)
    if year_match:
        citation.year = year_match.group(1)

    doi_match = DOI_RE.search(raw)
    if doi_match:
        citation.doi = doi_match.group(1).rstrip(".")

    pages_match = PAGES_RE.search(raw)
    if pages_match:
        groups = [g for g in pages_match.groups() if g]
        if groups:
            citation.pages = "-".join(groups[:2]) if len(groups) > 1 else groups[0]

    # Autoren: Text vor der Jahreszahl (oder vor dem ersten Punkt, falls kein Jahr)
    if year_match:
        citation.authors = raw[: year_match.start()].strip(" .,(")
    else:
        first_period = raw.find(". ")
        citation.authors = raw[:first_period].strip(" .,") if first_period > 0 else None

    # Titel: zwischen Jahr und nächstem Satzende (Punkt gefolgt von Großbuchstabe oder Ende)
    if year_match:
        rest = raw[year_match.end():].strip(" .,)")
        title_match = re.search(r"^(.*?)(?:\.\s|\.$)", rest)
        citation.title = (title_match.group(1) if title_match else rest[:200]).strip()

    return citation
