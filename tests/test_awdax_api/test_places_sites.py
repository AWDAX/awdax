"""Reading the website a Maps listing points to: emails, social links, site problems. No network: pages come from a dict."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

import places_pipeline  # noqa: E402
import places_search  # noqa: E402
import places_sites  # noqa: E402
import scraper  # noqa: E402
from places_sites import Fetched, Robots, enrich, pick_email, read_site  # noqa: E402
from places_strategy import places_table_schema, reconcile_places_intent  # noqa: E402
from reasoning import ScrapeIntent  # noqa: E402
from url_guard import UnresolvableHost, UnsafeURL  # noqa: E402


def cf_email(address: str, key: int = 0x4F) -> str:
    """How Cloudflare's email protection writes an address into a page."""
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in address)


HOME = """<!doctype html><html><head><title>Sharma Bakery – Noida</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="Fresh bread daily">
<meta name="generator" content="WordPress 6.4"><link rel="stylesheet" href="/wp-content/themes/x/style.css">
<script>var junk = "support@sentry.io";</script></head><body>
<nav><a href="/menu">Menu</a> <a href="/contact-us/">Contact us</a></nav>
<h1>Sharma Bakery</h1><p>We bake bread, cakes and pastries fresh every morning in Sector 18. Order for birthdays and weddings, with delivery across Noida and Delhi NCR. """ + "Family run since 1998. " * 20 + """</p>
<a href="https://www.instagram.com/sharmabakery/?hl=en">Instagram</a>
<a href="https://www.facebook.com/sharer/sharer.php?u=x">Share</a>
<a href="https://www.facebook.com/SharmaBakeryNoida">Facebook</a>
<a href="https://in.linkedin.com/company/sharma-bakery">LinkedIn</a>
<a href="https://wa.me/919876543210?text=hi">WhatsApp</a>
<a href="https://www.instagram.com/p/ABC123/">a post</a>
<a href="mailto:Orders@SharmaBakery.in?subject=Hello">Email us</a>
<footer>© 2019 Sharma Bakery. Write to info [at] sharmabakery [dot] in</footer></body></html>"""


class Pages:
    """A fake web: url -> Fetched, an exception to raise, or missing (404)."""

    def __init__(self, pages):
        self.pages, self.calls = dict(pages), []

    def __call__(self, url, max_bytes=0, timeout=0, verify=True):
        self.calls.append((url, verify))
        got = self.pages.get(url)
        if isinstance(got, BaseException):
            raise got
        if got is None:
            return Fetched(url, 404, "")
        return got if isinstance(got, Fetched) else Fetched(url, 200, got)


class ExtractionTests(unittest.TestCase):
    def read(self, html, url="https://sharmabakery.in/", **kw):
        return read_site(url, fetch=Pages({"https://sharmabakery.in/": html, "https://sharmabakery.in/robots.txt": ""}), now_year=2026, **kw)

    def test_a_homepage_gives_contact_details_social_links_and_platform(self):
        out = self.read(HOME)
        self.assertEqual(out["site_status"], "read")
        # two addresses on the page (a mailto and one written "info [at] ... [dot] in"): the generic one wins
        self.assertEqual(out["email"], "info@sharmabakery.in")
        self.assertEqual(out["contact_page"], "https://sharmabakery.in/contact-us/")
        self.assertEqual(out["instagram"], "https://www.instagram.com/sharmabakery/")
        self.assertEqual(out["facebook"], "https://www.facebook.com/SharmaBakeryNoida")
        self.assertEqual(out["linkedin"], "https://www.linkedin.com/company/sharma-bakery")
        self.assertEqual(out["whatsapp"], "https://wa.me/919876543210")
        self.assertEqual(out["site_platform"], "WordPress")

    def test_site_problems_are_named_plainly(self):
        out = self.read(HOME)
        self.assertEqual(out["site_notes"], "looks outdated (© 2019)")
        bare = self.read("<html><head><title>x</title></head><body><p>" + "word " * 100 + "</p></body></html>")
        self.assertEqual(bare["site_notes"], "not mobile friendly")
        http = read_site("http://sharmabakery.in/", fetch=Pages({"http://sharmabakery.in/": Fetched("http://sharmabakery.in/", 200, HOME.replace("2019", "2026"))}), now_year=2026)
        self.assertEqual(http["site_notes"], "no HTTPS")
        tiny = self.read("<html><head><meta name='viewport' content='x'></head><body>Hi</body></html>")
        self.assertIn("almost no readable text", tiny["site_notes"])

    def test_a_current_good_site_has_no_issues(self):
        out = self.read(HOME.replace("2019", "2026"))
        self.assertEqual(out["site_notes"], "")
        self.assertFalse(places_sites.is_weak_site(out))
        self.assertTrue(places_sites.is_weak_site({"site_status": "read", "site_notes": "no HTTPS"}))
        self.assertFalse(places_sites.is_weak_site({"site_status": "unreachable", "site_notes": "no HTTPS"}))

    def test_obfuscated_and_protected_emails_are_found(self):
        page = "<html><head><meta name='viewport' content='x'></head><body>" + "text " * 80 + "<a class='__cf_email__' data-cfemail='%s'>[email protected]</a></body></html>"
        self.assertEqual(self.read(page % cf_email("owner@sharmabakery.in"))["email"], "owner@sharmabakery.in")
        text = "<html><body>" + "text " * 80 + "Reach us: hello (at) sharmabakery (dot) in today</body></html>"
        self.assertEqual(self.read(text)["email"], "hello@sharmabakery.in")

    def test_the_contact_page_is_read_only_when_the_homepage_has_no_email(self):
        home = "<html><head><meta name='viewport' content='x'></head><body>" + "text " * 80 + "<a href='/contact'>Contact</a></body></html>"
        pages = Pages({"https://sharmabakery.in/": home, "https://sharmabakery.in/contact": "<html><body>Email: sales@sharmabakery.in <a href='https://www.instagram.com/sharma/'>ig</a></body></html>"})
        out = read_site("https://sharmabakery.in/", fetch=pages, now_year=2026)
        self.assertEqual((out["email"], out["instagram"], out["contact_page"]), ("sales@sharmabakery.in", "https://www.instagram.com/sharma/", "https://sharmabakery.in/contact"))
        self.assertIn(("https://sharmabakery.in/contact", True), pages.calls)
        again = Pages({"https://sharmabakery.in/": HOME, "https://sharmabakery.in/contact-us/": "<html>x@y.com</html>"})
        read_site("https://sharmabakery.in/", fetch=again, now_year=2026)
        self.assertNotIn("https://sharmabakery.in/contact-us/", [c[0] for c in again.calls], "an email was already found")

    def test_email_choice_prefers_the_sites_own_domain_and_a_role_people_write_to(self):
        self.assertEqual(pick_email(["x@gmail.com", "info@shop.in", "john@shop.in"], "shop.in"), "info@shop.in")
        self.assertEqual(pick_email(["owner@shop.in", "sales@shop.in"], "shop.in"), "sales@shop.in")
        self.assertEqual(pick_email(["a@gmail.com"], "shop.in"), "a@gmail.com", "a business on a free mailbox is still reachable")
        for bad in ("logo@2x.png", "a@sentry.io", "x@wixpress.com", "noreply@shop.in", "no-reply@shop.in", "user@example.com", "x@y", "a" * 90 + "@shop.in"):
            self.assertEqual(pick_email([bad], "shop.in"), "", bad)
        self.assertEqual(pick_email([], "shop.in"), "")

    def test_share_buttons_posts_and_widgets_are_not_profiles(self):
        html = """<html><head><meta name="viewport" content="x"></head><body><p>%s</p>
        <a href="https://www.facebook.com/sharer.php?u=1">s</a><a href="https://www.facebook.com/plugins/like.php">l</a>
        <a href="https://www.instagram.com/explore/tags/x/">e</a><a href="https://twitter.com/intent/tweet">t</a>
        <a href="https://www.linkedin.com/shareArticle?url=1">li</a><a href="tel:+911234567890">call</a><a href="javascript:void(0)">j</a>
        </body></html>""" % ("word " * 80)
        out = self.read(html)
        self.assertEqual((out["instagram"], out["facebook"], out["linkedin"], out["whatsapp"], out["email"]), ("", "", "", "", ""))

    def test_a_profile_link_with_an_id_is_kept(self):
        page = "<html><head><meta name='viewport' content='x'></head><body>" + "w " * 200 + "<a href='https://facebook.com/profile.php?id=100099'>f</a></body></html>"
        self.assertEqual(self.read(page)["facebook"], "https://www.facebook.com/profile.php?id=100099")

    def test_a_link_to_a_platform_is_not_the_platform_the_site_is_built_with(self):
        # python.org links to Blogger, Wix and Squarespace pages and uses none of them
        links = "<a href='https://blogger.com/'>b</a><a href='https://www.wix.com/'>w</a><a href='https://www.squarespace.com/'>s</a><a href='https://webflow.com'>f</a><a href='https://shopify.com'>sh</a>"
        out = self.read(f"<html><head><meta name='viewport' content='x'></head><body>{'w ' * 200}{links}</body></html>")
        self.assertEqual(out["site_platform"], "")

    def test_other_platforms_are_recognised(self):
        for marker, name in (("https://static.wixstatic.com/media/a.jpg", "Wix"), ("https://cdn.shopify.com/s/files/x.js", "Shopify"),
                             ("https://images.squarespace-cdn.com/x squarespace.com", "Squarespace"), ("<meta name='generator' content='Joomla! 4'>", "Joomla"), ("plain", "")):
            self.assertEqual(self.read(f"<html><head><meta name='viewport' content='x'>{marker}</head><body>{'w ' * 200}</body></html>")["site_platform"], name, marker)


class StatusTests(unittest.TestCase):
    def robots(self, text):
        return {"https://sharmabakery.in/robots.txt": text}

    def test_social_and_listing_pages_are_recorded_but_not_fetched(self):
        pages = Pages({})
        ig = read_site("https://www.instagram.com/sharmabakery/", fetch=pages)
        self.assertEqual((ig["site_status"], ig["instagram"]), ("social page only", "https://www.instagram.com/sharmabakery/"))
        fb = read_site("facebook.com/SharmaBakery", fetch=pages)
        self.assertEqual((fb["site_status"], fb["facebook"]), ("social page only", "https://www.facebook.com/SharmaBakery"))
        for url in ("https://sharma.business.site/", "https://www.zomato.com/noida/sharma-bakery", "https://goo.gl/maps/abc"):
            self.assertEqual(read_site(url, fetch=pages)["site_status"], "listing page, not its own website", url)
        self.assertEqual(pages.calls, [], "none of those were requested")

    def test_a_dead_website_is_said_so_and_counts_as_no_website_for_a_web_seller(self):
        cases = {
            "https://gone.in/": (UnresolvableHost("x"), "the listed website no longer exists"),
            "https://a.in/": (Fetched("https://a.in/", 404, "nope"), "the listed web page is gone"),
            "https://b.in/": (Fetched("https://b.in/", 410, "gone"), "the listed web page is gone"),
            "https://home.in/": (UnsafeURL("Blocked: address not allowed"), "the listed website does not lead to a working server"),
        }
        for url, (problem, note) in cases.items():
            out = read_site(url, fetch=Pages({url: problem}))
            self.assertEqual(out["site_notes"], note, url)
            self.assertTrue(places_sites.is_dead_site(out), url)
            self.assertFalse(places_sites.is_weak_site(out), "a dead site is not a site with problems")
        for status in ("unreachable (ReadTimeout)", "unreachable (HTTP 503)", "unreachable (HTTP 403)", "read", "social page only"):
            self.assertFalse(places_sites.is_dead_site({"site_status": status}), status)
        row = {"phone": "1", "rating": "4.6", "reviews": "80", "business_status": "Operational", "has_website": "yes", "site_status": "unreachable (the web address does not exist)", "site_notes": "x"}
        self.assertEqual(places_pipeline.lead_score(row, "web development"), 100, "same as a business with no website")
        self.assertEqual(places_pipeline.lead_score(row, "payroll services"), 70, "a dead website is no way in for anyone else")
        self.assertEqual(places_pipeline.lead_score({**row, "site_status": "unreachable (ReadTimeout)", "site_notes": ""}, "web development"), 70, "a slow site is not a dead one")

    def test_a_missing_or_unusable_address(self):
        self.assertEqual(read_site("", fetch=Pages({}))["site_status"], "no website")
        self.assertEqual(read_site("   ", fetch=Pages({}))["site_status"], "no website")
        self.assertEqual(read_site("localhost", fetch=Pages({}))["site_status"], "not a usable web address")

    def test_robots_txt_is_honoured(self):
        pages = Pages({**self.robots("User-agent: *\nDisallow: /\n"), "https://sharmabakery.in/": HOME})
        out = read_site("https://sharmabakery.in/", fetch=pages)
        self.assertEqual(out["site_status"], "not read: the site asks bots to stay out (robots.txt)")
        self.assertEqual([c[0] for c in pages.calls], ["https://sharmabakery.in/robots.txt"])
        ours = Pages({**self.robots(f"User-agent: {places_sites.BOT_NAME}\nDisallow: /\n"), "https://sharmabakery.in/": HOME})
        self.assertTrue(read_site("https://sharmabakery.in/", fetch=ours)["site_status"].startswith("not read"))
        elsewhere = Pages({**self.robots("User-agent: *\nDisallow: /admin\n"), "https://sharmabakery.in/": HOME})
        self.assertEqual(read_site("https://sharmabakery.in/", fetch=elsewhere)["site_status"], "read")

    def test_a_broken_robots_file_never_blocks(self):
        for robots in (RuntimeError("boom"), Fetched("https://sharmabakery.in/robots.txt", 500, "Disallow: /"), Fetched("https://sharmabakery.in/robots.txt", 200, "<html>not robots</html>")):
            pages = Pages({"https://sharmabakery.in/robots.txt": robots, "https://sharmabakery.in/": HOME})
            self.assertEqual(read_site("https://sharmabakery.in/", fetch=pages)["site_status"], "read")

    def test_robots_is_read_once_per_site(self):
        pages = Pages({"https://a.in/robots.txt": "", "https://a.in/x": "<html></html>"})
        robots = Robots(pages)
        for _ in range(3):
            robots.allows("https://a.in/x")
        self.assertEqual([c[0] for c in pages.calls], ["https://a.in/robots.txt"])

    def test_failures_become_a_status_not_an_exception(self):
        cases = {
            "https://sharmabakery.in/": (requests.ConnectionError("down"), "unreachable (Connection)"),
            "https://slow.in/": (requests.Timeout("slow"), "unreachable (Timeout)"),
            "https://gone.in/": (Fetched("https://gone.in/", 404, "nope"), "unreachable (HTTP 404)"),
            "https://err.in/": (Fetched("https://err.in/", 503, "busy"), "unreachable (HTTP 503)"),
            "https://private.in/": (UnsafeURL("Blocked: address not allowed"), "not read: address not allowed"),
            "https://nosuchsite.in/": (UnresolvableHost("could not resolve host"), "unreachable (the web address does not exist)"),
            "https://weird.in/": (ValueError("boom"), "unreachable"),
        }
        for url, (problem, expected) in cases.items():
            pages = Pages({url: problem})
            out = read_site(url, fetch=pages)
            self.assertEqual(out["site_status"], expected, url)
            self.assertEqual(out["email"], "")

    def test_a_site_that_refuses_bots_but_sends_a_page_is_still_read(self):
        big = Fetched("https://sharmabakery.in/", 403, HOME)
        self.assertEqual(read_site("https://sharmabakery.in/", fetch=Pages({"https://sharmabakery.in/": big}), now_year=2026)["site_status"], "read")

    def test_a_bad_certificate_is_read_anyway_and_noted(self):
        class Bad(Pages):
            def __call__(self, url, max_bytes=0, timeout=0, verify=True):
                self.calls.append((url, verify))
                if url.endswith("robots.txt"):
                    return Fetched(url, 404, "")
                if verify:
                    raise requests.exceptions.SSLError("certificate has expired")
                return Fetched(url, 200, HOME.replace("2019", "2026"))

        pages = Bad({})
        out = read_site("https://sharmabakery.in/", fetch=pages, now_year=2026)
        self.assertEqual(out["site_status"], "read")
        self.assertIn("HTTPS certificate problem", out["site_notes"])
        self.assertIn(("https://sharmabakery.in/", False), pages.calls)

    def test_a_bare_domain_gets_https_and_the_page_that_loaded_is_the_one_read(self):
        pages = Pages({"https://sharmabakery.in": Fetched("https://www.sharmabakery.in/home", 200, HOME.replace("2019", "2026"))})
        out = read_site("sharmabakery.in", fetch=pages, now_year=2026)
        self.assertEqual(out["site_status"], "read")
        self.assertEqual(out["contact_page"], "https://www.sharmabakery.in/contact-us/", "links resolve against where the page really was")
        self.assertEqual(out["email"], "info@sharmabakery.in")

    def test_the_real_fetch_goes_through_the_address_guard(self):
        resp = mock.Mock(status_code=200, text="<html>ok</html>", url="https://a.in/")
        with mock.patch.object(places_sites, "safe_get", return_value=resp) as safe:
            got = places_sites.default_fetch("https://a.in/", 1234, 7.0, False)
        self.assertEqual((got.status, got.text, got.url), (200, "<html>ok</html>", "https://a.in/"))
        kwargs = safe.call_args.kwargs
        self.assertEqual((kwargs["max_bytes"], kwargs["timeout"], kwargs["verify"]), (1234, 7.0, False))
        self.assertIn("AWDAXBot", kwargs["headers"]["User-Agent"])
        with self.assertRaises(UnsafeURL):  # a listing that points at a private address is refused, not fetched
            places_sites.default_fetch("http://127.0.0.1/", 1000, 3.0)
        with self.assertRaises(UnsafeURL):
            places_sites.default_fetch("http://169.254.169.254/latest/meta-data/", 1000, 3.0)


class EnrichTests(unittest.TestCase):
    def rows(self):
        return [
            {"name": "A", "website": "https://a.in/", "lead_score": "90"},
            {"name": "B", "website": "https://www.a.in/branch", "lead_score": "80"},  # same site as A
            {"name": "C", "website": "", "lead_score": "70"},
            {"name": "D", "website": "https://d.in/", "lead_score": "60"},
        ]

    def fake_read(self, seen):
        def read(url, **kw):
            seen.append(url)
            out = {k: "" for k in places_sites.SITE_KEYS}
            out.update(site_status="read", email=f"hi@{places_sites._host(url)}")
            return out

        return read

    def test_each_site_is_read_once_and_every_listing_on_it_gets_the_result(self):
        seen, rows = [], self.rows()
        stats = enrich(rows, read=self.fake_read(seen), workers=2)
        self.assertEqual(sorted(seen), ["https://a.in/", "https://d.in/"])
        self.assertEqual([r["email"] for r in rows], ["hi@a.in", "hi@a.in", "", "hi@d.in"])
        self.assertEqual(rows[2]["site_status"], "no website")
        self.assertEqual(stats, {"sites": 2, "read": 2, "emails": 2, "failed": 0, "skipped": 0})
        self.assertTrue(all(set(places_sites.SITE_KEYS) <= set(r) for r in rows))

    def test_the_site_limit_and_the_time_budget_stop_the_run_and_say_so(self):
        rows = [{"website": f"https://s{i}.in/", "lead_score": str(100 - i)} for i in range(10)]
        seen = []
        stats = enrich(rows, read=self.fake_read(seen), workers=2, max_sites=3)
        self.assertEqual((len(seen), stats["read"], stats["skipped"]), (3, 3, 7))
        self.assertTrue(all("limit" in r["site_status"] for r in rows[3:]))
        rows = [{"website": f"https://t{i}.in/"} for i in range(10)]
        ticks = iter([0, 0, 999, 999, 999, 999, 999, 999])
        stats = enrich(rows, read=self.fake_read([]), workers=2, clock=lambda: next(ticks), time_budget_s=10)
        self.assertEqual(stats["read"] + stats["skipped"], 10)
        self.assertGreater(stats["skipped"], 0)

    def test_progress_is_reported_after_each_batch_and_a_deleted_chat_stops_it(self):
        rows = [{"website": f"https://s{i}.in/"} for i in range(9)]
        batches = []
        enrich(rows, read=self.fake_read([]), workers=2, on_batch=lambda done, total: batches.append((done, total)))
        self.assertEqual(batches, [(4, 9), (8, 9), (9, 9)])

        class Gone(Exception):
            pass

        def dead():
            raise Gone()

        with self.assertRaises(Gone):
            enrich(rows, read=self.fake_read([]), check_alive=dead)

    def test_failed_reads_are_counted(self):
        def read(url, **kw):
            return {**{k: "" for k in places_sites.SITE_KEYS}, "site_status": "unreachable (HTTP 404)"}

        stats = enrich([{"website": "https://x.in/"}], read=read)
        self.assertEqual((stats["read"], stats["failed"]), (0, 1))


class SchemaAndScoreTests(unittest.TestCase):
    def intent(self, **env):
        with mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "k", **env}, clear=False):
            return reconcile_places_intent(ScrapeIntent(job_id="j", topic="bakeries", raw_prompt="bakeries in noida", geography="Noida", pipeline="places",
                                                        places={"search_terms": ["bakeries"], "locations": ["Noida"]}))

    def test_website_columns_are_part_of_a_maps_table_by_default(self):
        schema = places_table_schema(self.intent())
        self.assertEqual(len(schema["columns"]), len(schema["column_labels"]))
        for col in places_sites.SITE_KEYS:
            self.assertIn(col, schema["columns"])
        self.assertLess(schema["columns"].index("website"), schema["columns"].index("email"))
        self.assertEqual(schema["columns"][-2:], ["lead_score", "matched_query"])

    def test_it_can_be_turned_off_by_the_owner_or_the_request(self):
        self.assertFalse(self.intent(PLACES_SCRAPE_SITES="0").places["scrape_sites"])
        self.assertNotIn("email", places_table_schema(self.intent(PLACES_SCRAPE_SITES="off"))["columns"])
        with mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "k"}):
            said_no = reconcile_places_intent(ScrapeIntent(job_id="j", topic="t", raw_prompt="cafes in pune", geography="Pune", pipeline="places",
                                                           places={"search_terms": ["cafes"], "locations": ["Pune"], "scrape_sites": False}))
        self.assertFalse(said_no.places["scrape_sites"])

    def test_a_weak_site_is_a_better_prospect_for_a_web_seller_and_an_email_is_a_way_in(self):
        base = {"phone": "1", "rating": "4.6", "reviews": "80", "business_status": "Operational", "has_website": "yes", "site_status": "read"}
        plain = places_pipeline.lead_score({**base, "site_notes": ""}, "web development")
        weak = places_pipeline.lead_score({**base, "site_notes": "no HTTPS"}, "web development")
        self.assertEqual((plain, weak), (70, 90))
        self.assertEqual(places_pipeline.lead_score({**base, "site_notes": "no HTTPS", "email": "a@b.in"}, "web development"), 95)
        self.assertEqual(places_pipeline.lead_score({**base, "site_notes": "no HTTPS"}, "payroll services"), 100, "a site problem means nothing to someone selling something else")
        self.assertEqual(places_pipeline.lead_score({**base, "site_notes": "", "email": "a@b.in"}, "payroll services"), 100, "capped")
        self.assertEqual(places_pipeline.lead_score({**base, "has_website": "no", "site_notes": "x"}, "web development"), 100)


class RunIntegrationTests(unittest.TestCase):
    """The whole Maps run, with the website step on: places in, website facts and re-ranked scores out."""

    def setUp(self):
        self.stored, self.tables = [], []

        class Service:
            def store_record(s, job_id, url, row, plan=None):
                self.stored.append(dict(row))
                return {"id": len(self.stored)}

            def save_merged_table(s, job_id, table):
                self.tables.append(table)

            def emit_event(s, *a, **k):
                pass

        for patch in (
            mock.patch.object(scraper, "universal_service", Service()),
            mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "k", "PLACES_WORKERS": "2"}),
            mock.patch.object(places_search, "charge"),
            mock.patch.object(places_search, "register_job"),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.progress = []

    def search(self, query, **kw):
        return [
            {"id": "p1", "displayName": {"text": "Has Site"}, "googleMapsUri": "https://maps.google.com/?cid=1", "websiteUri": "https://hassite.in/", "nationalPhoneNumber": "1", "rating": 4.5, "userRatingCount": 100, "businessStatus": "OPERATIONAL"},
            {"id": "p2", "displayName": {"text": "No Site"}, "googleMapsUri": "https://maps.google.com/?cid=2", "nationalPhoneNumber": "2", "rating": 4.5, "userRatingCount": 100, "businessStatus": "OPERATIONAL"},
            {"id": "p3", "displayName": {"text": "Old Site"}, "googleMapsUri": "https://maps.google.com/?cid=3", "websiteUri": "https://oldsite.in/", "nationalPhoneNumber": "3", "rating": 4.5, "userRatingCount": 100, "businessStatus": "OPERATIONAL"},
        ], None

    def run_job(self, **cfg_over):
        cfg = {"search_terms": ["bakeries"], "locations": ["Noida"], "target_count": 3, "extra_fields": [], "lead_focus": "web development", "scrape_sites": True, **cfg_over}
        intent = ScrapeIntent(job_id="job1", topic="bakeries", raw_prompt="leads", pipeline="places", places=cfg)
        sess = {"id": "c1", "table_schema": places_table_schema(intent)}
        pages = Pages({
            "https://hassite.in/robots.txt": "", "https://oldsite.in/robots.txt": "",
            "https://hassite.in/": HOME.replace("2019", "2026"), "https://oldsite.in/": Fetched("http://oldsite.in/", 200, "<html><body>" + "old page " * 60 + "© 2015 Old Site. old@oldsite.in</body></html>"),
        })
        with mock.patch.object(places_search, "geocode", return_value=None), mock.patch.object(places_search, "search_text", side_effect=self.search), \
                mock.patch.object(places_sites, "default_fetch", pages):
            return places_pipeline.run_places_job(sess, intent, user_id="u", on_progress=lambda p, m: self.progress.append(m))

    def test_websites_are_read_and_the_leads_are_re_ranked(self):
        stats = self.run_job()
        rows = {r["name"]: r for r in self.tables[-1]["rows"]}
        self.assertEqual(rows["Has Site"]["email"], "info@sharmabakery.in")  # the page's own text names this address
        self.assertEqual(rows["Has Site"]["instagram"], "https://www.instagram.com/sharmabakery/")
        self.assertEqual(rows["Old Site"]["email"], "old@oldsite.in")
        self.assertEqual(rows["Old Site"]["site_notes"], "no HTTPS; not mobile friendly; looks outdated (© 2015)")
        self.assertEqual(rows["No Site"]["site_status"], "no website")
        # a web seller: no website first, then the site with the most to fix, then the good site
        self.assertEqual([r["name"] for r in self.tables[-1]["rows"]], ["No Site", "Old Site", "Has Site"])
        self.assertEqual(stats["websites"]["read"], 2)
        self.assertEqual(stats["websites"]["emails"], 2)
        self.assertTrue(any("Reading 2 business websites" in m for m in self.progress))
        self.assertTrue(any(m.startswith("Read ") and "of 2 business websites" in m for m in self.progress))
        self.assertEqual(set(self.tables[-1]["rows"][0]), set(self.tables[-1]["columns"]))
        enriched = {r["name"]: r for r in self.stored}
        self.assertEqual(enriched["Old Site"]["email"], "old@oldsite.in", "the stored record matches the table")

    def test_turned_off_it_reads_nothing(self):
        with mock.patch.object(places_sites, "enrich", side_effect=AssertionError("no website must be opened")):
            stats = self.run_job(scrape_sites=False)
        self.assertIsNone(stats["websites"])
        self.assertNotIn("email", self.tables[-1]["columns"])


if __name__ == "__main__":
    unittest.main()
