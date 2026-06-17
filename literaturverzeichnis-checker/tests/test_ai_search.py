from src.verify.ai_search import (
    _extract_gemini_grounding_sources,
    _extract_openrouter_grounding_sources,
    extract_doi_from_url,
)


def test_extract_doi_from_url_matches_doi_org_link():
    assert extract_doi_from_url("https://doi.org/10.1016/s0378-5122") == "10.1016/s0378-5122"


def test_extract_doi_from_url_strips_trailing_punctuation():
    assert extract_doi_from_url("https://doi.org/10.1016/s0378-5122.") == "10.1016/s0378-5122"


def test_extract_doi_from_url_returns_none_for_non_doi_link():
    assert extract_doi_from_url("https://example.com/some-article") is None


def test_gemini_extracts_grounding_chunks_into_sources():
    candidate = {
        "content": {"parts": [{"text": "{}"}]},
        "groundingMetadata": {
            "groundingChunks": [
                {"web": {"uri": "https://doi.org/10.1016/s0378-5122", "title": "Ein Titel"}},
                {"web": {"uri": "https://example.com/other"}},
            ]
        },
    }
    sources = _extract_gemini_grounding_sources(candidate)
    assert len(sources) == 2
    assert sources[0].url == "https://doi.org/10.1016/s0378-5122"
    assert sources[0].title == "Ein Titel"
    assert sources[1].title is None


def test_gemini_returns_empty_grounding_sources_when_metadata_absent():
    candidate = {"content": {"parts": [{"text": "{}"}]}}
    assert _extract_gemini_grounding_sources(candidate) == []


def test_openrouter_extracts_url_citation_annotations_into_sources():
    message = {
        "content": "{}",
        "annotations": [
            {
                "type": "url_citation",
                "url_citation": {"url": "https://doi.org/10.1016/s0378-5122", "title": "Ein Titel"},
            },
            {"type": "something_else"},
        ],
    }
    sources = _extract_openrouter_grounding_sources(message)
    assert len(sources) == 1
    assert sources[0].url == "https://doi.org/10.1016/s0378-5122"
    assert sources[0].title == "Ein Titel"


def test_openrouter_returns_empty_grounding_sources_when_no_annotations():
    message = {"content": "{}"}
    assert _extract_openrouter_grounding_sources(message) == []
