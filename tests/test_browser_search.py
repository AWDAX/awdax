import base64

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import discovery.browser_search as bs
import discovery.url_discovery as ud
from discovery.gather import gather_candidates
from discovery.schemas import DorkPlan, SearchHit

GOAL = "Track how many ev cars have been sold by mahindra since jan 2026"


def _bing_link(url: str) -> str:
    token = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return f"https://www.bing.com/ck/a?!&&p=abc&u=a1{token}&ntb=1"


def test_unwrap_bing_decodes_url_safe_base64():
    url = "https://www.rushlane.com/mahindra-sales-jan-2026?utm=a>b~c??"
    link = _bing_link(url)
    assert "-" in link or "_" in link  # the case plain b64decode got wrong
    assert bs._unwrap_bing_url(link) == url


def test_unwrap_bing_never_returns_a_bing_link():
    assert bs._unwrap_bing_url("https://www.bing.com/ck/a?!&&p=abc&ntb=1") is None
    assert bs._unwrap_bing_url("https://www.bing.com/images/search?q=ev") is None
    assert bs._unwrap_bing_url("https://www.cardekho.com/electric-cars#top") == "https://www.cardekho.com/electric-cars"


class _Anchor:
    def __init__(self, href: str, text: str) -> None:
        self.href, self.text = href, text

    def get_attribute(self, _name: str) -> str:
        return self.href

    def inner_text(self) -> str:
        return self.text


class _Page:
    """Fake Playwright page: the first read can hit a mid-navigation error, results can be missing."""

    def __init__(self, *, destroyed_once: bool = False, results: bool = True) -> None:
        self.destroyed_once, self.results, self.reads = destroyed_once, results, 0

    def goto(self, _url: str, **_kw) -> None:
        pass

    def wait_for_selector(self, _selector: str, timeout: int) -> None:
        if not self.results:
            raise PlaywrightTimeoutError(f"Timeout {timeout}ms exceeded.")

    def query_selector_all(self, _selector: str) -> list[_Anchor]:
        self.reads += 1
        if self.destroyed_once and self.reads == 1:
            raise PlaywrightError("Execution context was destroyed, most likely because of a navigation")
        return [_Anchor(_bing_link("https://www.carwale.com/mahindra-cars/"), "Mahindra Cars")]


def test_bing_retries_once_after_a_mid_navigation_error():
    page = _Page(destroyed_once=True)
    hits = bs._scrape_bing(page, "mahindra ev price")
    assert [h.url for h in hits] == ["https://www.carwale.com/mahindra-cars/"]
    assert page.reads == 2


def test_bing_without_results_is_empty_not_an_error():
    assert bs._scrape_bing(_Page(results=False), "zzzz no results") == []


def test_bing_first_and_ddg_skipped_after_it_fails():
    calls: list[tuple[str, str]] = []
    hit = SearchHit(url="https://example.com/a", title="a", snippet="")

    def bing(_page, q, *, max_results=10):
        calls.append(("bing", q))
        return [hit] if q == "found" else []

    def ddg(_page, q, *, max_results=10):
        calls.append(("ddg", q))
        raise TimeoutError("bot check")

    original = bs._scrape_bing, bs._scrape_ddg
    bs._scrape_bing, bs._scrape_ddg = bing, ddg
    try:
        state = bs._EngineState()
        assert bs._search_on_page(None, "found", state=state) == [hit]
        assert bs._search_on_page(None, "nothing", state=state) == []
        assert bs._search_on_page(None, "nothing again", state=state) == []
    finally:
        bs._scrape_bing, bs._scrape_ddg = original
    assert calls == [("bing", "found"), ("bing", "nothing"), ("ddg", "nothing"), ("bing", "nothing again")]


def test_gather_searches_the_planned_queries_then_falls_back():
    searched: list[list[str]] = []
    original = ud.browser_search_queries
    ud.browser_search_queries = lambda qs, **_kw: searched.append(list(qs)) or []
    try:
        plan = DorkPlan(intent_summary="Mahindra EV sales", dork_queries=["q1", "q2", "q3", "q4"])
        common = dict(tried_queries={"q2"}, skip_urls=set(), dork_batch=3)
        _, offset, strategies = gather_candidates(GOAL, plan, dork_offset=0, expansion_round=0, **common)
        assert (offset, strategies) == (3, ["q1", "q2", "q3"])
        gather_candidates(GOAL, plan, dork_offset=3, expansion_round=0, **common)
        gather_candidates(GOAL, plan, dork_offset=6, expansion_round=1, **common)
    finally:
        ud.browser_search_queries = original
    assert searched[0] == ["q1", "q3"]  # q2 was already tried
    assert searched[1] == ["q4"]
    assert searched[2] == bs.search_query_variants(GOAL, 1)  # plan used up
