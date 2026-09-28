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


def test_search_query_text_does_not_make_junk_look_relevant():
    query = "best electric cars under 20 lakh India price"
    hits = [
        # What Bing returned for that query: the snippet is only our own query text.
        SearchHit(url="https://www.merriam-webster.com/dictionary/best", title="Best Definition & Meaning",
                  snippet=f"Bing: {query}", from_dork=query),
        SearchHit(url="https://www.everydayhealth.com/", title="Everyday Health", snippet=f"Bing: {query}", from_dork=query),
        SearchHit(url="https://www.zigwheels.com/newcars/electric-cars", title="Electric Cars in India",
                  snippet=f"Bing: {query}", from_dork=query),
    ]
    ranked = filter_and_rank_hits(query, hits)
    assert [h.url for h in ranked] == ["https://www.zigwheels.com/newcars/electric-cars"]
