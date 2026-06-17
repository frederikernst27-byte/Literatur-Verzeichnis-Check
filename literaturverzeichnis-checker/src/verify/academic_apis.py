"""Abfrage kostenloser akademischer APIs (CrossRef, OpenAlex, Semantic Scholar)
und Fuzzy-Matching gegen die geparste Zitatangabe. Kein API-Key nötig.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests
from rapidfuzz import fuzz

TIMEOUT = 10
TITLE_MATCH_THRESHOLD = 80  # ab hier gilt ein Treffer als "wahrscheinlich dieselbe Quelle"


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


def find_best_candidate(title: str, authors: str | None = None) -> tuple[Candidate | None, float]:
    """Fragt alle drei APIs ab und gibt den plausibelsten Kandidaten zurück
    (zusammen mit dem Titel-Ähnlichkeits-Score 0-100).

    Die Auswahl gewichtet Titel- UND Autoren-Ähnlichkeit, damit bei mehreren
    ähnlich betitelten Treffern (z.B. unterschiedliche Paper mit ähnlichem
    Titel) nicht versehentlich der falsche als Treffer gilt.
    """
    if not title or len(title.strip()) < 5:
        return None, 0.0

    candidates: list[Candidate] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(query_fn, title)
            for query_fn in (query_crossref, query_openalex, query_semantic_scholar)
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


def compare_to_citation(citation, candidate: Candidate, title_score: float) -> list[str]:
    """Vergleicht die geparste Zitatangabe mit dem gefundenen Kandidaten und
    gibt eine Liste konkreter Abweichungen zurück."""
    discrepancies = []

    if citation.year and candidate.year and citation.year != candidate.year:
        discrepancies.append(f"Jahr weicht ab: Zitat nennt {citation.year}, gefunden wurde {candidate.year}")

    if citation.authors and candidate.authors:
        author_str = " ".join(candidate.authors).lower()
        cited_authors = [a.strip() for a in re_split_authors(citation.authors)]
        for cited in cited_authors:
            if not cited:
                continue
            author_score = fuzz.partial_ratio(cited.lower(), author_str)
            if author_score < 70:
                discrepancies.append(f"Autor '{cited}' im Original nicht in gefundener Quelle wiedergefunden (evtl. falsch geschrieben)")

    if citation.pages and not candidate.url:
        pass  # Seitenangaben werden von den APIs i.d.R. nicht geliefert -> nicht prüfbar

    if title_score < 95:
        discrepancies.append(f"Titel weicht leicht ab (Ähnlichkeit {title_score:.0f}%): gefunden '{candidate.title}'")

    return discrepancies


def re_split_authors(authors_str: str) -> list[str]:
    parts = re.split(r";|\band\b|&|,(?=\s*[A-ZÄÖÜ][a-zäöü]+,)", authors_str)
    return [p.strip(" .,") for p in parts if p.strip(" .,")]
