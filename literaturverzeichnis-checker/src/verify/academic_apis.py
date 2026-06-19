"""Abfrage kostenloser akademischer APIs (CrossRef, OpenAlex, Semantic Scholar)
und Fuzzy-Matching gegen die geparste Zitatangabe. Kein API-Key nötig.
"""
from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests
from rapidfuzz import fuzz

TIMEOUT = 10
TITLE_MATCH_THRESHOLD = 60  # ab hier gilt ein Treffer als "wahrscheinlich dieselbe Quelle"


@dataclass
class Candidate:
    source_api: str
    title: str
    authors: list[str]
    year: str | None
    doi: str | None
    venue: str | None
    url: str | None


def _safe_get(url: str, **kwargs):
    try:
        resp = requests.get(url, timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def query_crossref_by_doi(doi: str) -> Candidate | None:
    """Exakter Lookup über die CrossRef-DOI-API. Liefert bei Erfolg einen
    eindeutigen Treffer zurück - kein Fuzzy-Matching nötig, da der DOI das
    Werk eindeutig identifiziert."""
    data = _safe_get(f"https://api.crossref.org/works/{doi}")
    if not data:
        return None
    item = data.get("message")
    if not item:
        return None
    authors = [
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in item.get("author", [])
    ]
    year = None
    date_parts = item.get("issued", {}).get("date-parts", [[None]])
    if date_parts and date_parts[0]:
        year = str(date_parts[0][0]) if date_parts[0][0] else None
    return Candidate(
        source_api="crossref",
        title=(item.get("title") or [""])[0],
        authors=authors,
        year=year,
        doi=item.get("DOI"),
        venue=(item.get("container-title") or [None])[0],
        url=item.get("URL"),
    )


def query_crossref(title: str, rows: int = 3) -> list[Candidate]:
    data = _safe_get(
        "https://api.crossref.org/works",
        params={"query.bibliographic": title, "rows": rows},
    )
    if not data:
        return []
    out = []
    for item in data.get("message", {}).get("items", []):
        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in item.get("author", [])
        ]
        year = None
        date_parts = item.get("issued", {}).get("date-parts", [[None]])
        if date_parts and date_parts[0]:
            year = str(date_parts[0][0]) if date_parts[0][0] else None
        out.append(
            Candidate(
                source_api="crossref",
                title=(item.get("title") or [""])[0],
                authors=authors,
                year=year,
                doi=item.get("DOI"),
                venue=(item.get("container-title") or [None])[0],
                url=item.get("URL"),
            )
        )
    return out


def query_openalex(title: str, per_page: int = 3) -> list[Candidate]:
    data = _safe_get(
        "https://api.openalex.org/works",
        params={"search": title, "per-page": per_page},
    )
    if not data:
        return []
    out = []
    for item in data.get("results", []):
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in item.get("authorships", [])
        ]
        out.append(
            Candidate(
                source_api="openalex",
                title=item.get("title") or "",
                authors=authors,
                year=str(item.get("publication_year")) if item.get("publication_year") else None,
                doi=(item.get("doi") or "").replace("https://doi.org/", "") or None,
                venue=(item.get("host_venue") or {}).get("display_name"),
                url=item.get("id"),
            )
        )
    return out


def query_semantic_scholar(title: str, limit: int = 3) -> list[Candidate]:
    data = _safe_get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={"query": title, "limit": limit, "fields": "title,authors,year,externalIds,venue,url"},
    )
    if not data:
        return []
    out = []
    for item in data.get("data", []):
        out.append(
            Candidate(
                source_api="semanticscholar",
                title=item.get("title") or "",
                authors=[a.get("name", "") for a in item.get("authors", [])],
                year=str(item.get("year")) if item.get("year") else None,
                doi=(item.get("externalIds") or {}).get("DOI"),
                venue=item.get("venue"),
                url=item.get("url"),
            )
        )
    return out


def query_core(title: str, limit: int = 3) -> list[Candidate]:
    """CORE API – 200M+ Open-Access-Paper, gut für Konferenzbeiträge und Preprints."""
    data = _safe_get(
        "https://api.core.ac.uk/v3/search/works",
        params={"q": title, "limit": limit},
    )
    if not data:
        return []
    out = []
    for item in data.get("results", []):
        authors = [a.get("name", "") for a in (item.get("authors") or [])]
        doi = item.get("doi") or None
        year = str(item.get("yearPublished")) if item.get("yearPublished") else None
        urls = item.get("sourceFulltextUrls") or []
        out.append(
            Candidate(
                source_api="core",
                title=item.get("title") or "",
                authors=authors,
                year=year,
                doi=doi,
                venue=item.get("publisher"),
                url=urls[0] if urls else item.get("downloadUrl"),
            )
        )
    return out


def get_all_candidates(title: str) -> list[Candidate]:
    """Gibt alle Kandidaten aus CrossRef, OpenAlex, Semantic Scholar und CORE zurück."""
    if not title or len(title.strip()) < 5:
        return []
    candidates: list[Candidate] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(query_fn, title)
            for query_fn in (query_crossref, query_openalex, query_semantic_scholar, query_core)
        ]
        for future in futures:
            candidates.extend(future.result())
    return candidates


def find_best_candidate(
    title: str, authors: str | None = None, doi: str | None = None
) -> tuple[Candidate | None, float]:
    """Fragt alle drei APIs ab und gibt den plausibelsten Kandidaten zurück
    (zusammen mit dem Titel-Ähnlichkeits-Score 0-100).

    Ist ein DOI bekannt, wird zuerst ein exakter Lookup darüber versucht -
    das ist zuverlässiger als Fuzzy-Titelsuche und liefert bei Erfolg Score
    100. Nur wenn das fehlschlägt (oder kein DOI vorliegt), wird auf die
    Fuzzy-Suche über alle drei APIs zurückgefallen.

    Die Auswahl gewichtet Titel- UND Autoren-Ähnlichkeit, damit bei mehreren
    ähnlich betitelten Treffern (z.B. unterschiedliche Paper mit ähnlichem
    Titel) nicht versehentlich der falsche als Treffer gilt.
    """
    if doi:
        doi_match = query_crossref_by_doi(doi)
        if doi_match:
            return doi_match, 100.0

    if not title or len(title.strip()) < 5:
        return None, 0.0

    candidates: list[Candidate] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(query_fn, title)
            for query_fn in (query_crossref, query_openalex, query_semantic_scholar, query_core)
        ]
        for future in futures:
            candidates.extend(future.result())

    cited_authors = re_split_authors(authors) if authors else []

    best, best_title_score, best_combined_score = None, 0.0, -1.0
    for c in candidates:
        if not c.title:
            continue
        title_score = fuzz.token_sort_ratio(title.lower(), c.title.lower())

        author_score = 100.0
        if cited_authors and c.authors:
            candidate_author_str = " ".join(c.authors).lower()
            per_author_scores = [
                fuzz.partial_ratio(a.lower(), candidate_author_str) for a in cited_authors
            ]
            author_score = sum(per_author_scores) / len(per_author_scores)

        combined_score = 0.65 * title_score + 0.35 * author_score
        if combined_score > best_combined_score:
            best, best_title_score, best_combined_score = c, title_score, combined_score

    return best, best_title_score


def _normalize(s: str) -> str:
    """Normalisiert Umlaute und entfernt Akzente für robustes Fuzzy-Matching.
    ü→ue, ä→ae, ö→oe, ß→ss, dann ASCII-only lowercased."""
    s = s.replace("ü", "ue").replace("Ü", "Ue")
    s = s.replace("ä", "ae").replace("Ä", "Ae")
    s = s.replace("ö", "oe").replace("Ö", "Oe")
    s = s.replace("ß", "ss")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()


def compare_to_citation(citation, candidate: Candidate, title_score: float) -> list[str]:
    """Vergleicht die geparste Zitatangabe mit dem gefundenen Kandidaten und
    gibt eine Liste konkreter Abweichungen zurück."""
    discrepancies = []

    # ±1 Jahr tolerieren (Online-first vs. Print-Datum ist normal)
    if citation.year and candidate.year:
        try:
            if abs(int(citation.year) - int(candidate.year)) > 1:
                discrepancies.append(
                    f"Jahr weicht ab: Zitat nennt {citation.year}, gefunden wurde {candidate.year}"
                )
        except ValueError:
            pass

    if citation.authors and candidate.authors:
        # Normalisierte API-Autoren als Suchraum
        author_str_norm = _normalize(" ".join(candidate.authors))
        cited_authors = re_split_authors(citation.authors)
        unmatched = []
        for cited in cited_authors:
            if not cited:
                continue
            # Nur Nachnamen vergleichen (erster Token vor Leerzeichen/Komma)
            last_name = re.split(r"[\s,]", cited)[0]
            if len(last_name) < 3:
                continue  # Initiale allein überspringen
            score = fuzz.partial_ratio(_normalize(last_name), author_str_norm)
            if score < 70:
                unmatched.append(cited)
        if unmatched:
            discrepancies.append(
                f"Autor(en) nicht gefunden: {', '.join(unmatched[:3])}"
                + (" (evtl. Umlaut-/Schreibweise)" if any(
                    c in "".join(unmatched) for c in "äöüÄÖÜß"
                ) else "")
            )

    if title_score < 95:
        discrepancies.append(f"Titel weicht leicht ab (Ähnlichkeit {title_score:.0f}%): gefunden '{candidate.title}'")

    return discrepancies


def re_split_authors(authors_str: str) -> list[str]:
    """Splittet Autorenlisten in verschiedenen Formaten:
    - "Nygaard I, Barber MD, Burgio KL" (Nachname + Initialen, kommagetrennt)
    - "Smith, John; Jones, Mary" (invertiert, semikolongetrennt)
    - "Smith J and Jones M" (mit 'and')
    """
    clean = re.sub(r"\s+et\s+al\.?\s*$", "", authors_str, flags=re.IGNORECASE).strip()

    # Semikolon/and/& zuerst probieren
    parts = re.split(r";|\band\b|&", clean)
    if len(parts) > 1:
        return [p.strip(" .,") for p in parts if p.strip(" .,")]

    # Komma vor Großbuchstabe + Kleinbuchstabe = neuer Nachname
    # Matcht "Nygaard I, Barber MD" weil "Barber" mit 'B'+'a' beginnt
    parts = re.split(r",\s*(?=[A-ZÄÖÜ][a-zäöü])", clean)
    if len(parts) > 1:
        return [p.strip(" .,") for p in parts if p.strip(" .,")]

    # Fallback: alles als eine Einheit
    return [clean] if clean else []
