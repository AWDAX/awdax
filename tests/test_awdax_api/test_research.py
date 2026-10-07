"""Research first: Google search through Gemini's REST API and the ranked top-5 websites."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gemini_search  # noqa: E402
import web_research  # noqa: E402
from reasoning import ScrapeIntent  # noqa: E402


def _intent(prompt="give me parliamentary debates in india between 2010 to 2025"):
    return ScrapeIntent(job_id="job-r", topic="Indian parliamentary debates", raw_prompt=prompt, geography="India")


def _rest_answer(text, chunks=(), queries=()):
    return {
        "candidates": [{
            "content": {"parts": [{"text": text}]},
            "groundingMetadata": {"webSearchQueries": list(queries), "groundingChunks": [{"web": {"title": t, "uri": u}} for t, u in chunks]},
        }]
    }


class GroundedSearchTests(unittest.TestCase):
    def post(self, *responses):
        res = [mock.Mock(status_code=s, text=str(b)[:50], json=mock.Mock(return_value=b)) for s, b in responses]
        return mock.patch.object(gemini_search.requests, "post", side_effect=res)

    def test_the_google_search_tool_is_sent_as_json_and_the_answer_and_its_sources_are_read(self):
        body = _rest_answer('{"x": 1}', chunks=[("sansad.in", "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc")], queries=["lok sabha debates"])
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k", "GEMINI_MODEL": ""}), self.post((200, body)) as post:
            answer = gemini_search.grounded_answer("find")
        sent = post.call_args.kwargs
        self.assertEqual(sent["json"]["tools"], [{"google_search": {}}])
        self.assertEqual(sent["headers"], {"x-goog-api-key": "k"})
        self.assertIn("gemini-3.5-flash", post.call_args.args[0])
        self.assertEqual((answer.text, answer.queries), ('{"x": 1}', ["lok sabha debates"]))
        self.assertEqual(answer.source_domains(), {"sansad.in"})

    def test_a_retired_model_falls_back_and_other_errors_are_reported(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k", "GEMINI_MODEL": ""}), self.post((404, {}), (200, _rest_answer("ok"))) as post:
            self.assertEqual(gemini_search.grounded_answer("q").text, "ok")
        self.assertIn("gemini-flash-latest", post.call_args.args[0])
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), self.post((400, {}), (400, {})), self.assertRaises(RuntimeError):
            gemini_search.grounded_answer("q")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}), self.assertRaises(RuntimeError):
            gemini_search.grounded_answer("q")

    def test_search_queries_get_real_pages_back(self):
        import source_search

        answer = gemini_search.GroundedAnswer(text='{"pages": [{"url": "https://sansad.in/ls/debates", "title": "LS"}, {"url": "ftp://x"}]}')
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch.object(gemini_search, "grounded_answer", return_value=answer):
            self.assertEqual([h["url"] for h in source_search._gemini_grounded_search("lok sabha debates", _intent())], ["https://sansad.in/ls/debates"])
        cited = gemini_search.GroundedAnswer(text="no json here", sources=[{"title": "prsindia.org", "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/z"}])
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch.object(gemini_search, "grounded_answer", return_value=cited), \
                mock.patch.object(gemini_search, "resolve_redirect", return_value="https://prsindia.org/sessiontrack"):
            self.assertEqual([h["url"] for h in source_search._gemini_grounded_search("q", _intent())], ["https://prsindia.org/sessiontrack"])

    def test_pages_google_cited_come_before_pages_the_model_named_and_redirects_never_leak(self):
        import source_search

        redirect = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a"
        answer = gemini_search.GroundedAnswer(
            text='{"pages": [{"url": "https://sansad.in/rs/debates"}, {"url": "%s"}, {"url": "https://sansad.in/rs/debates/officials/"}]}' % redirect,
            sources=[{"title": "sansad.in", "url": redirect}],
        )
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch.object(gemini_search, "grounded_answer", return_value=answer), \
                mock.patch.object(gemini_search, "resolve_redirect", return_value="https://sansad.in/rs/debates/officials"):
            urls = [h["url"] for h in source_search._gemini_grounded_search("q", _intent())]
        self.assertEqual(urls, ["https://sansad.in/rs/debates/officials", "https://sansad.in/rs/debates"])

    def test_a_redirect_that_cannot_be_resolved_is_dropped(self):
        answer = gemini_search.GroundedAnswer(sources=[{"title": "x.test", "url": "https://vertexaisearch.cloud.google.com/r/1"}])
        with mock.patch.object(gemini_search.requests, "head", side_effect=gemini_search.requests.ConnectionError("down")):
            self.assertEqual(gemini_search.cited_pages(answer), [])
        with mock.patch.object(gemini_search.requests, "head", return_value=mock.Mock(headers={"location": "https://x.test/list"})):
            self.assertEqual(gemini_search.cited_pages(answer), [{"url": "https://x.test/list", "title": "x.test"}])


class ResearchTests(unittest.TestCase):
    ANSWER = """```json
{"understanding": "Debates of both Houses, 2010-2025",
 "websites": [
  {"rank": 2, "url": "https://sansad.in/rs/debates/officials", "site_name": "Rajya Sabha", "what_it_has": "RS debates", "format": "search results"},
  {"rank": 1, "url": "http://sansad.in/ls/debates/digitized", "site_name": "Lok Sabha", "what_it_has": "LS debates"},
  {"rank": 3, "url": "not a url"},
  {"rank": 4, "url": "https://sansad.in/rs/debates/officials"},
  {"rank": 5, "url": "https://prsindia.org/sessiontrack", "site_name": "PRS"},
  {"rank": 6, "url": "https://zenodo.org/records/1"},
  {"rank": 7, "url": "https://example.org/extra"}
 ]}
```"""

    def research(self, answer, n=None, env=None):
        reply = gemini_search.GroundedAnswer(text=answer, queries=["lok sabha debates 2010"], sources=[{"title": "sansad.in", "url": "https://vertexaisearch.cloud.google.com/r/1"}])
        cited = [{"url": "https://sansad.in/ls/debates/digitized", "title": "sansad.in"}, {"url": "https://sansad.in/rs/debates/officials", "title": "sansad.in"}]
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k", **(env or {})}), mock.patch.object(gemini_search, "grounded_answer", return_value=reply) as call, \
                mock.patch.object(gemini_search, "cited_pages", return_value=cited):
            return web_research.research_top_sites(_intent(), n=n), call

    def test_a_ranked_site_carries_the_pages_google_cited_on_the_same_site(self):
        out, _ = self.research('{"websites": [{"rank": 1, "url": "https://sansad.in/ls/debates"}, {"rank": 2, "url": "https://prsindia.org/x"}]}')
        self.assertEqual(out["websites"][0]["alt_urls"], ["https://sansad.in/ls/debates/digitized", "https://sansad.in/rs/debates/officials"])
        self.assertEqual(out["websites"][1]["alt_urls"], [])

    def test_the_ranking_is_kept_cleaned_and_capped_at_five(self):
        out, call = self.research(self.ANSWER)
        self.assertEqual([s["url"] for s in out["websites"]], [
            "https://sansad.in/ls/debates/digitized", "https://sansad.in/rs/debates/officials", "https://prsindia.org/sessiontrack",
            "https://zenodo.org/records/1", "https://example.org/extra",
        ])
        self.assertEqual([s["rank"] for s in out["websites"]], [1, 2, 3, 4, 5])
        self.assertEqual([s["grounded"] for s in out["websites"]], ["yes", "yes", "no", "no", "no"])
        self.assertEqual(out["understanding"], "Debates of both Houses, 2010-2025")
        self.assertEqual(out["searched"], ["lok sabha debates 2010"])
        prompt = call.call_args.args[0]
        self.assertIn("give me parliamentary debates in india between 2010 to 2025", prompt)
        self.assertIn("Never invent a URL", prompt)
        self.assertIn("Give exactly 5 websites", prompt)

    def test_the_prompt_names_no_site_or_topic_of_its_own(self):
        flights = ScrapeIntent(job_id="j", topic="flights", raw_prompt="cheapest flights from delhi to goa", geography="India")
        prompt = web_research.build_prompt(flights, 5)
        for word in ("sansad", "parliament", "wikipedia", "cardekho", "debate"):
            self.assertNotIn(word, prompt.lower())

    def test_no_search_or_a_failed_one_leaves_discovery_as_before(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.assertEqual(web_research.research_top_sites(_intent())["websites"], [])
        out, _ = self.research(self.ANSWER, env={"RESEARCH_FIRST": "0"})
        self.assertEqual(out["websites"], [])
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch.object(gemini_search, "grounded_answer", side_effect=RuntimeError("down")):
            self.assertEqual(web_research.research_top_sites(_intent())["websites"], [])
        out, _ = self.research("Try https://prsindia.org/sessiontrack and https://sansad.in/ls/debates.")
        self.assertEqual([s["url"] for s in out["websites"]], ["https://prsindia.org/sessiontrack", "https://sansad.in/ls/debates"])


if __name__ == "__main__":
    unittest.main()
