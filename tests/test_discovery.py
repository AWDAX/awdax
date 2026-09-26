from discovery.discover import format_discovery_message
from discovery.schemas import RankedSource, SourceRankingResult
from discovery.search import dedupe_hits
from discovery.schemas import SearchHit


def test_dedupe_hits_normalizes_urls():
    hits = [
        SearchHit(url="https://Example.com/path/", title="a", snippet=""),
        SearchHit(url="https://example.com/path", title="b", snippet=""),
    ]
    assert len(dedupe_hits(hits)) == 1


def test_format_discovery_message_includes_scores():
    result = SourceRankingResult(
        summary="EV sales in India",
        sources=[
            RankedSource(
                url="https://data.gov.in",
                title="Open data",
                why_good="Official portal",
                data_format_guess="csv",
                authority_score=9,
                relevance_score=8,
            )
        ],
    )
    text = format_discovery_message(result, dork_queries=['site:data.gov.in "electric"'])
    assert "data.gov.in" in text
    assert "Authority 9/10" in text
    assert "site:data.gov.in" in text
