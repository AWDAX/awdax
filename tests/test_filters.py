from discovery.filters import filter_and_rank_hits, is_blocked_url
from discovery.schemas import SearchHit


def test_blocks_wikipedia():
    assert is_blocked_url("https://en.wikipedia.org/wiki/India")


def test_prefers_automotive_for_ev_goal():
    hits = [
        SearchHit(url="https://en.wikipedia.org/wiki/Electricity", title="Electricity", snippet=""),
        SearchHit(
            url="https://www.cardekho.com/electric-cars",
            title="Electric Cars",
            snippet="ex-showroom price",
        ),
    ]
    ranked = filter_and_rank_hits("list all ev cars in india with prices", hits)
    assert ranked[0].url.startswith("https://www.cardekho.com")
