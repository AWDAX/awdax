# Spec BK: backend fixes (owner approved backend edits on 2026-10-02: "keep backend changes small")

Repo root: `X:\Hackathons\Codecubicle\awdax-audit` (Flask backend at root, branch `fix/stability-pass`).
Python: `.venv/Scripts/python.exe`. Tests: `.venv/Scripts/python.exe -m unittest discover -s tests/test_awdax_api -t tests/test_awdax_api` (13 pass today).
Rules: smallest change, no new pip packages (use `requests`, already a dependency), never read or print `.env`, files under 300 lines
where you create them (existing big files: edit in place, do not refactor). Do NOT touch anything under `Frontend/`. Do NOT commit; the lead commits.
Add tests as new files in `tests/test_awdax_api/` using `unittest` + `unittest.mock` (no network, no real keys).

## BK1. NVIDIA LLM provider (owner's keys are NVIDIA ones)

Env names (owner's): `NVIDIA_API_KEY`, `NVIDIA_API_BASE`, `LLM_MODEL`. Also accept `NVIDIA_BASE_URL`, `NVIDIA_MODELS` (csv), `NVIDIA_TIMEOUT_SECONDS` (default 90).
Pattern to copy (name it in a comment): `X:\Hackathons\Codecubicle\awdax\Backend\llm\nvidia.py` and `llm\gemini.py` (owner's earlier branch `feat/nvidia-llm`); read them, but port to `requests`, not httpx/pydantic.

1. New `llm_client.py` at repo root:
   - `llm_json(prompt: str, *, temperature: float = 0.2) -> Any` and `llm_text(prompt: str, *, temperature: float = 0.2) -> str`.
   - Order: NVIDIA when `NVIDIA_API_KEY` is set → Gemini when `GEMINI_API_KEY` is set → else `RuntimeError("No LLM key set: add NVIDIA_API_KEY (or GEMINI_API_KEY) to .env")`.
   - NVIDIA: base = `NVIDIA_API_BASE` or `NVIDIA_BASE_URL` or `https://integrate.api.nvidia.com/v1` (strip trailing `/`). Models = `LLM_MODEL` first (if set), then `NVIDIA_MODELS` csv,
     default csv `nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning,nvidia/nemotron-3.5-lightning-30b-a3b,nvidia/nemotron-3-super-120b-a12b`; de-duplicate, keep order.
     POST `{base}/chat/completions` with `{"model", "messages":[{"role":"user","content":prompt}], "temperature", "max_tokens": 8192}` and `Authorization: Bearer <key>`, timeout from env.
     Read `choices[0].message.content`. Strip `<think>…</think>` blocks. For JSON: strip ``` fences, take the outermost `{…}` or `[…]` (whichever starts first), `json.loads`.
     On 401/403: remember "key rejected" for the process and stop trying NVIDIA (fall through to Gemini). On any other failure (HTTP error, timeout, bad JSON): log a warning (never the key) and try the next model.
     If all NVIDIA models fail and no Gemini key: raise `RuntimeError` naming the last error (no key in the message).
   - Gemini: move the current body of `reasoning.gemini_json` here (same model env `GEMINI_MODEL`, same fence stripping).
2. `reasoning.gemini_json(prompt, *, temperature=0.2)` keeps its name and signature and just returns `llm_json(prompt, temperature=temperature)`
   (12 call sites import it; do not touch them).
3. `RegulatoryFeed.py` has four blocks that call Gemini directly (around lines 320–550, `_gemini_summary` and siblings). Each currently returns `None`/falls back when
   `GEMINI_API_KEY` is missing. Change each so it calls `llm_text(prompt)` when either key is set, keeping its existing parsing and its existing fallback on any exception.
   Keep the change mechanical.
4. `source_search.py` grounded Google search is Gemini-only: leave it; just confirm it returns `[]` without a Gemini key (it does).
5. Tests `test_llm_client.py`: NVIDIA success with `<think>` + fenced JSON; `LLM_MODEL` tried first; 500 on model 1 → model 2 answers; 401 → no further NVIDIA calls and,
   with no Gemini key, a RuntimeError without the key text; no keys → the "No LLM key set" error. Patch `requests.post` and `os.environ` (use `mock.patch.dict(os.environ, {...}, clear=True)`).

## BK2. Concurrency hunks from branch commit `c590915` (port by hand; do NOT merge or cherry-pick the commit)

Read `git show c590915 -- RegulatoryFeed.py ui_sessions.py scraper.py app.py`. Take only:
- `ui_sessions._conn` and `RegulatoryFeed._get_db`: `sqlite3.connect(..., timeout=10.0, check_same_thread=False)` then `PRAGMA journal_mode = WAL;`, `PRAGMA busy_timeout = 10000;`, `PRAGMA synchronous = NORMAL;`
  (10 s, not 30 s: `ui_sessions` holds a process-wide lock while it waits, and Cloudflare gives up at 100 s).
- `RegulatoryFeed._ensure_pdf_text` and `_generate_summary_for`: close the DB connection before the PDF download / LLM call and reopen to write (the c590915 restructuring).
- `RegulatoryFeed.trigger_scrape`: set `self.is_running = True` **before** `t.start()` (inside the existing lock); if `t.start()` raises, set it back to False and re-raise.
- `scraper.UniversalScrapeService.trigger_scrape_all`: `self._running_jobs.add(jid)` before `t.start()` (keep the existing add/discard inside `_run_all`; adding twice to a set is harmless).
- `app.py` `/api/events`: `sub.get(timeout=1.0)` instead of `0.05`.
Do NOT take c590915's `save_session` title-preservation, `update_session_title`, routes.py or NewChat.tsx changes.
Also in `ui_sessions.py`: make `init_ui_sessions()` run its DDL once per process (module-level `_initialized` flag checked/set under `_lock`); callers stay unchanged.

## BK3. Lost updates and titles

- `awdax_api/orchestrator.py` `_run_thread`: where it refreshes keys from `latest` before the final persist, add `"title"`, `"archived"`, `"keep_live"` to the tuple, so a rename,
  archive or pause made during a run is not overwritten when the run ends.
- `awdax_api/routes.py` `create_instance`: cap the title at 80 chars (`title[:80].strip()`), same rule `post_message` already uses.
- Test: simulate `_run_thread`'s final merge with a session renamed mid-run (patch `run_pipeline_for_session` to rename via `persist_session` before returning) → final title is the rename.

## BK4. eGazette only when the user asks for it

Today any "government data" prompt can be routed to the eGazette feed, because the model may set `pipeline: regulatory_feed` and `_intent_blob` includes model-written fields.
- `regulatory_strategy.intent_uses_regulatory_feed(intent)`: True only when the **user's own text** (`intent.raw_prompt`, falling back to `intent.topic` when raw_prompt is empty)
  matches `_EGAZETTE_RE`, extended to also match the plain word `gazette`/`gazettes`. Ignore `intent.pipeline`, `named_sites`, `constraints`, `entity_types` for this decision.
- `enrich_intent_for_execution`: when the model chose `regulatory_feed` but the check above is False, set `intent.pipeline = "universal"` and return.
- `reasoning.parse_prompt` system text: say "Set pipeline to "regulatory_feed" ONLY when the user explicitly mentions eGazette, egazette.gov.in or gazette notifications; otherwise "universal"."
- Tests: "get all sessions of Rajya Sabha and Lok Sabha debates" with model pipeline `regulatory_feed` → universal; "latest egazette notifications from ministry of finance" → regulatory;
  "Track EV prices in India" → universal; "gazette notifications this week" → regulatory.

## BK5. Per-user access on every instance route

- `awdax_api/session_store.load_instance_session(instance_id, user_id=None)` passes `user_id` to `get_session`. Background code keeps calling it without a user (unchanged).
- `awdax_api/routes.py`: every route under `/api/instances/<instance_id>…` (GET, PATCH, DELETE, messages GET/POST, dataset GET/DELETE, dashboard, live GET/PATCH, live/stream,
  sources, dataset/stats, dataset/rescore, graph/parameters, graph, and the WebSocket in `register_websocket`) loads with `get_user_id(request)` and returns the existing 404 when not found.
  DELETE must load (scoped) **before** calling `stop_live`.
- `auth_helper.get_user_id`:
  - Trust `X-User-Id` only when env `PROXY_SHARED_SECRET` is unset (today's behaviour, for local dev) **or** the request's `X-Proxy-Secret` header equals it (`hmac.compare_digest`).
    If the secret is set and the header is missing/wrong, ignore `X-User-Id` and continue to the Authorization path.
  - When `SUPABASE_JWT_SECRET` is set and signature verification fails, return `"anonymous"` (remove the unverified-decode fallback in that branch). Keep the no-secret unverified decode (local dev).
- Tests with Flask's test client (`app.test_client()` from `app.py`; point `ui_sessions.DB_PATH` at a temp file the way existing tests do): A creates, B (different `X-User-Id`) gets 404 on GET/PATCH/DELETE/messages and A's list excludes nothing;
  secret set + wrong header → X-User-Id ignored; secret set + right header → trusted.

## Done for BK

All old and new tests pass (run the command above and paste the summary line). Then start the server briefly to be sure it imports:
`.venv/Scripts/python.exe -c "import app"` must print no traceback. Report: files changed, test counts, anything you could not do and why.
