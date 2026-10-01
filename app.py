import json
import logging
import os
import queue
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

ROOT = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

from RegulatoryFeed import feed_service  # noqa: E402
from discovery import SourceCandidate  # noqa: E402
from inspector import (  # noqa: E402
    ScrapePlan,
    discover_inspected_sources,
    egazette_preset_plan,
    inspect_all_sources,
    inspect_source,
)
from reasoning import ScrapeIntent, parse_prompt  # noqa: E402
from regulatory_strategy import (  # noqa: E402
    intent_uses_regulatory_feed,
    regulatory_feed_max_pages,
    regulatory_feed_table_schema,
)
from scraper import ScrapeJob, run_pipeline, universal_service  # noqa: E402
from ui_sessions import (  # noqa: E402
    create_session,
    delete_session,
    ensure_default_session,
    get_session,
    list_sessions,
    save_session,
)


from auth_helper import get_user_id

app = Flask(__name__)

from awdax_api import init_awdax_api  # noqa: E402

init_awdax_api(app)


def _session_id_from_request(body: dict | None = None) -> str | None:
    data = body if body is not None else (request.get_json(silent=True) or {})
    return (
        data.get("session_id")
        or request.headers.get("X-Session-Id")
        or request.args.get("session_id")
    )


def _work_session(body: dict | None = None) -> dict:
    sid = _session_id_from_request(body)
    if sid:
        found = get_session(sid, get_user_id(request))
        if found:
            return found
        raise ValueError(f"Unknown session: {sid}")
    return ensure_default_session(get_user_id(request))


def _public_session(sess: dict) -> dict:
    return {
        "id": sess["id"],
        "title": sess.get("title"),
        "job_id": sess.get("job_id"),
        "intent": sess.get("intent"),
        "search_queries": sess.get("search_queries") or [],
        "table_schema": sess.get("table_schema"),
        "sources": sess.get("sources") or [],
        "plans": sess.get("plans") or [],
        "plan": sess.get("plan"),
        "prompt_draft": sess.get("prompt_draft") or "",
        "keep_live": bool(sess.get("keep_live")),
    }


def _trigger_regulatory_feed_scrape(*, max_pages: int | None = None) -> dict:
    pages = regulatory_feed_max_pages(max_pages)
    result = feed_service.trigger_scrape(max_pages=pages)
    return {
        **result,
        "pipeline": "regulatory_feed",
        "max_pages": pages,
        "message": (
            "RegulatoryFeed scrape started (listing + PDF + AI summaries)"
            if result.get("started")
            else "RegulatoryFeed scrape already running"
        ),
    }


def _empty_session_feed(*, session_id: str | None = None) -> dict:
    return {
        "ok": True,
        "view": "empty",
        "count": 0,
        "rows": [],
        "items": [],
        "source": "session",
        "session_scoped": True,
        "session_id": session_id,
    }


def _sessions_with_flags() -> list[dict]:
    overview = universal_service.get_overview()
    live = set(overview.get("live_job_ids") or [])
    running = set(overview.get("running_job_ids") or [])
    out: list[dict] = []
    for row in list_sessions(get_user_id(request)):
        jid = row.get("job_id")
        out.append(
            {
                **row,
                "live": bool(jid and jid in live),
                "running": bool(jid and jid in running),
            }
        )
    return out


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/api/sessions")
def api_sessions_list():
    try:
        overview = universal_service.get_overview()
        return jsonify({"ok": True, "sessions": _sessions_with_flags(), **overview})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/sessions")
def api_sessions_create():
    try:
        body = request.get_json(silent=True) or {}
        title = str(body.get("title") or "New session").strip() or "New session"
        sess = create_session(get_user_id(request), title=title)
        return jsonify({"ok": True, "session": _public_session(sess)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/sessions/<session_id>")
def api_sessions_get(session_id: str):
    try:
        sess = get_session(session_id, get_user_id(request))
        if not sess:
            return jsonify({"ok": False, "error": "Session not found"}), 404
        jid = sess.get("job_id")
        return jsonify(
            {
                "ok": True,
                "session": _public_session(sess),
                "live": universal_service.is_job_live(jid),
                "running": universal_service.is_job_running(jid),
                "status": universal_service.get_job_status(jid) if jid else None,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.patch("/api/sessions/<session_id>")
def api_sessions_patch(session_id: str):
    try:
        body = request.get_json(silent=True) or {}
        sess = get_session(session_id, get_user_id(request))
        if not sess:
            return jsonify({"ok": False, "error": "Session not found"}), 404
        if body.get("title"):
            sess["title"] = str(body["title"]).strip()[:120] or sess.get("title")
        for key in (
            "prompt_draft",
            "intent",
            "search_queries",
            "table_schema",
            "sources",
            "plan",
            "plans",
            "job_id",
            "keep_live",
        ):
            if key in body:
                sess[key] = body[key]
        saved = save_session(get_user_id(request), sess)
        return jsonify({"ok": True, "session": _public_session(saved)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.delete("/api/sessions/<session_id>")
def api_sessions_delete(session_id: str):
    try:
        sess = get_session(session_id, get_user_id(request))
        if not sess:
            return jsonify({"ok": False, "error": "Session not found"}), 404
        jid = sess.get("job_id")
        if jid and universal_service.is_job_live(jid):
            universal_service.stop_live(jid)
        if not delete_session(session_id, get_user_id(request)):
            return jsonify({"ok": False, "error": "Session not found"}), 404
        remaining = list_sessions(get_user_id(request))
        fallback = get_session(remaining[0]["id"], get_user_id(request)) if remaining else create_session(get_user_id(request), title="Session 1")
        return jsonify(
            {
                "ok": True,
                "deleted": session_id,
                "active_session": _public_session(fallback),
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/feed")
def api_feed():
    try:
        limit = min(int(os.getenv("FEED_LIMIT", "50")), 200)
    except ValueError:
        limit = 50
    sess = None
    sid = request.args.get("session_id")
    if sid:
        sess = get_session(sid, get_user_id(request))
        if not sess:
            return jsonify({"ok": False, "error": "Session not found"}), 404
    job_id = request.args.get("job_id")
    if job_id == "":
        job_id = None
    if job_id is None and sess:
        job_id = sess.get("job_id")
    if sid and not job_id:
        return jsonify(_empty_session_feed(session_id=sid))
    try:
        merged = universal_service.get_merged_table(job_id)
        if not merged and job_id:
            raw = universal_service.list_raw_records(job_id, limit=500)
            if raw:
                intent = None
                if sess and sess.get("intent") and sess.get("job_id") == job_id:
                    intent = ScrapeIntent.from_dict(sess["intent"])
                else:
                    intent = universal_service.load_intent(job_id)
                if intent:
                    from table_merge import merge_records

                    table = merge_records(intent, raw)
                    if table.get("rows"):
                        universal_service.save_merged_table(job_id, table)
                        merged = table
        if merged and merged.get("rows"):
            return jsonify(
                {
                    "ok": True,
                    "view": "table",
                    "columns": merged["columns"],
                    "column_labels": merged["column_labels"],
                    "rows": merged["rows"],
                    "count": merged["row_count"],
                    "source": "universal",
                }
            )
        if job_id:
            universal_items = universal_service.list_records(job_id, limit=limit)
            if universal_items:
                return jsonify(
                    {
                        "ok": True,
                        "view": "cards",
                        "count": len(universal_items),
                        "items": universal_items,
                        "source": "universal",
                        "job_id": job_id,
                    }
                )
            intent = None
            if sess and sess.get("intent"):
                intent = ScrapeIntent.from_dict(sess["intent"])
            if intent and intent_uses_regulatory_feed(intent):
                items = feed_service.list_feed(limit=limit)
                return jsonify(
                    {
                        "ok": True,
                        "view": "cards",
                        "count": len(items),
                        "items": items,
                        "source": "regulatory",
                        "pipeline": "regulatory_feed",
                        "job_id": job_id,
                    }
                )
            return jsonify({**_empty_session_feed(session_id=sid), "job_id": job_id})
        items = feed_service.list_feed(limit=limit)
        return jsonify({"ok": True, "count": len(items), "items": items, "source": "regulatory"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/scrape/status")
def api_scrape_status():
    reg = feed_service.get_scrape_status()
    uni = universal_service.get_scrape_status()
    overview = universal_service.get_overview()
    running = reg.get("is_running") or uni.get("is_running")
    job_id = request.args.get("job_id")
    job_status = universal_service.get_job_status(job_id) if job_id else None
    return jsonify(
        {
            "ok": True,
            "is_running": running,
            "regulatory": reg,
            "universal": uni,
            "job_status": job_status,
            **overview,
        }
    )


@app.get("/api/events")
def api_events():
    """SSE: regulatory feed + universal scraper events."""

    @stream_with_context
    def generate():
        subs = [feed_service.subscribe_events(), universal_service.subscribe_events()]
        try:
            payload = {
                "type": "connected",
                **feed_service.get_scrape_status(),
                "universal": universal_service.get_scrape_status(),
                **universal_service.get_overview(),
            }
            yield f"data: {json.dumps(payload, default=str)}\n\n"
            while True:
                sent = False
                for sub in subs:
                    try:
                        event = sub.get(timeout=0.05)
                        yield f"data: {json.dumps(event, default=str)}\n\n"
                        sent = True
                    except queue.Empty:
                        continue
                if not sent:
                    yield ": keepalive\n\n"
        finally:
            feed_service.unsubscribe_events(subs[0])
            universal_service.unsubscribe_events(subs[1])

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/scrape/live/stop")
def api_scrape_live_stop():
    try:
        body = request.get_json(silent=True) or {}
        job_id = body.get("job_id")
        if not job_id:
            try:
                sess = _work_session(body)
                job_id = sess.get("job_id")
            except ValueError as e:
                return jsonify({"ok": False, "error": str(e)}), 404
        result = universal_service.stop_live(job_id)
        try:
            sess = _work_session(body)
            if sess.get("job_id") == job_id or not job_id:
                sess["keep_live"] = False
                save_session(get_user_id(request), sess)
        except ValueError:
            pass
        return jsonify({"ok": True, "message": "Live mode stopped", **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/scrape/start")
def api_scrape_start():
    try:
        max_pages = int(os.getenv("SCRAPE_MAX_PAGES", "3"))
        result = feed_service.trigger_scrape(max_pages=max_pages)
        if result.get("started"):
            msg = "Regulatory scrape started."
        else:
            msg = "Regulatory scrape already running."
        return jsonify({"ok": True, "message": msg, **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/prompt")
def api_prompt():
    try:
        body = request.get_json(silent=True) or {}
        text = (body.get("prompt") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "prompt required"}), 400
        sess = _work_session(body)
        intent = parse_prompt(text)
        sess["intent"] = intent.to_dict()
        sess["job_id"] = intent.job_id
        sess["search_queries"] = []
        sess["table_schema"] = None
        sess["sources"] = []
        sess["plan"] = None
        sess["plans"] = []
        sess["title"] = (intent.topic or text)[:120]
        sess = save_session(get_user_id(request), sess)
        job = ScrapeJob(job_id=intent.job_id, intent=intent, status="intent_ready")
        universal_service.save_job(job)
        return jsonify({"ok": True, "intent": intent.to_dict(), "session": _public_session(sess)})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/queries")
def api_queries():
    try:
        body = request.get_json(silent=True) or {}
        sess = _work_session(body)
        if body.get("intent"):
            intent = ScrapeIntent.from_dict(body["intent"])
        elif sess.get("intent"):
            intent = ScrapeIntent.from_dict(sess["intent"])
        else:
            return jsonify({"ok": False, "error": "Run /api/prompt first"}), 400

        from query_generation import generate_search_queries

        queries = generate_search_queries(intent)
        sess["search_queries"] = [q.to_dict() for q in queries]
        sess["job_id"] = intent.job_id
        sess = save_session(get_user_id(request), sess)
        return jsonify(
            {
                "ok": True,
                "queries": sess["search_queries"],
                "count": len(queries),
                "session": _public_session(sess),
            }
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/table-headers")
def api_table_headers():
    try:
        body = request.get_json(silent=True) or {}
        sess = _work_session(body)
        if not sess.get("intent"):
            return jsonify({"ok": False, "error": "Run /api/prompt first"}), 400
        if not sess.get("plans"):
            return jsonify({"ok": False, "error": "Run discover & inspect first"}), 400
        intent = ScrapeIntent.from_dict(sess["intent"])
        plans = [ScrapePlan.from_dict(p) for p in sess["plans"]]

        if intent_uses_regulatory_feed(intent):
            schema = regulatory_feed_table_schema()
        elif body.get("columns") and body.get("column_labels"):
            schema = {
                "columns": list(body["columns"]),
                "column_labels": list(body["column_labels"]),
                "description": str(body.get("description") or ""),
            }
        else:
            from table_schema import propose_table_schema

            schema = propose_table_schema(intent, plans)

        sess["table_schema"] = schema
        sess["job_id"] = intent.job_id
        sess = save_session(get_user_id(request), sess)
        return jsonify({"ok": True, "table_schema": schema, "session": _public_session(sess)})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/discover")
def api_discover():
    try:
        body = request.get_json(silent=True) or {}
        sess = _work_session(body)
        if body.get("intent"):
            intent = ScrapeIntent.from_dict(body["intent"])
        elif sess.get("intent"):
            intent = ScrapeIntent.from_dict(sess["intent"])
        else:
            return jsonify({"ok": False, "error": "Run /api/prompt first"}), 400
        progress: list[str] = []
        jid = intent.job_id

        def _on_progress(msg: str) -> None:
            progress.append(msg)
            universal_service.emit_event(
                "log",
                {"level": "info", "message": msg, "job_id": jid, "channel": "universal"},
            )

        search_queries = body.get("queries") or sess.get("search_queries") or None
        if not search_queries and not intent_uses_regulatory_feed(intent):
            return jsonify(
                {
                    "ok": False,
                    "error": "Run /api/queries first to generate Google search queries",
                }
            ), 400

        sources, plans = discover_inspected_sources(
            intent,
            on_progress=_on_progress,
            search_queries=search_queries,
        )
        sess["sources"] = [s.to_dict() for s in sources]
        sess["plans"] = [p.to_dict() for p in plans]
        sess["plan"] = plans[0].to_dict() if plans else None
        sess["job_id"] = intent.job_id
        sess = save_session(get_user_id(request), sess)
        universal_service.save_job(
            ScrapeJob(job_id=intent.job_id, intent=intent, plans=plans, status="plans_ready")
        )
        inspected = [
            {
                "source": p.source_name,
                "url": p.source_url or p.entry_url,
                "dry_run_rows": p.dry_run_rows,
                "blocked": p.blocked,
                "confidence": p.confidence,
                "warnings": p.warnings[:3],
            }
            for p in plans
        ]
        return jsonify(
            {
                "ok": True,
                "sources": sess["sources"],
                "plans": sess["plans"],
                "inspected": inspected,
                "count": len(sources),
                "target": min(int(intent.max_sources or 10), int(os.getenv("DISCOVERY_MAX_SOURCES", "10"))),
                "progress": progress[-20:],
                "session": _public_session(sess),
            }
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/inspect")
def api_inspect():
    try:
        body = request.get_json(silent=True) or {}
        inspect_all = body.get("inspect_all", True)
        sess = _work_session(body)
        if not sess.get("sources"):
            return jsonify({"ok": False, "error": "Run /api/discover first"}), 400
        intent = ScrapeIntent.from_dict(sess["intent"])
        sources = [SourceCandidate.from_dict(s) for s in sess["sources"]]

        if inspect_all:
            plans = inspect_all_sources(intent, sources)
            sess["plans"] = [p.to_dict() for p in plans]
            sess["plan"] = plans[0].to_dict() if plans else None
            sess = save_session(get_user_id(request), sess)
            universal_service.save_job(
                ScrapeJob(job_id=intent.job_id, intent=intent, plans=plans, status="plans_ready")
            )
            return jsonify(
                {
                    "ok": True,
                    "plans": sess["plans"],
                    "count": len(plans),
                    "session": _public_session(sess),
                    "summary": [
                        {
                            "source": p.source_name,
                            "url": p.source_url or p.entry_url,
                            "dry_run_rows": p.dry_run_rows,
                            "blocked": p.blocked,
                            "confidence": p.confidence,
                        }
                        for p in plans
                    ],
                }
            )

        idx = int(body.get("source_index", 0))
        if idx >= len(sources):
            idx = 0
        source = sources[idx]
        plan = inspect_source(intent, source)
        sess["plan"] = plan.to_dict()
        sess["plans"] = [plan.to_dict()]
        sess = save_session(get_user_id(request), sess)
        universal_service.save_job(
            ScrapeJob(job_id=intent.job_id, intent=intent, source=source, plan=plan, plans=[plan], status="plan_ready")
        )
        return jsonify({"ok": True, "plan": plan.to_dict(), "source": source.to_dict(), "session": _public_session(sess)})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/scrape/run")
def api_scrape_run():
    try:
        body = request.get_json(silent=True) or {}
        max_pages_raw = body.get("max_pages")
        max_pages = int(max_pages_raw) if max_pages_raw is not None else None
        use_preset = bool(body.get("use_egazette_preset"))
        sess = _work_session(body)

        session_intent = (
            ScrapeIntent.from_dict(sess["intent"]) if sess.get("intent") else None
        )
        use_regulatory_feed = use_preset or (
            session_intent is not None and intent_uses_regulatory_feed(session_intent)
        )

        if use_regulatory_feed:
            if use_preset:
                intent = ScrapeIntent.from_dict(
                    sess.get("intent") or {"job_id": "egazette", "topic": "eGazette", "pipeline": "regulatory_feed"}
                )
            else:
                intent = session_intent
            plan = egazette_preset_plan()
            sess["plan"] = plan.to_dict()
            sess["plans"] = [plan.to_dict()]
            sess["job_id"] = intent.job_id
            sess["intent"] = intent.to_dict()
            sess = save_session(get_user_id(request), sess)
            result = _trigger_regulatory_feed_scrape(max_pages=max_pages)
            return jsonify(
                {
                    "ok": True,
                    **result,
                    "job_id": intent.job_id,
                    "session": _public_session(sess),
                }
            )
        elif sess.get("plans") or sess.get("plan"):
            scrape_max = int(max_pages_raw or os.getenv("SCRAPE_MAX_PAGES", "3"))
            if not sess.get("table_schema"):
                return jsonify({"ok": False, "error": "Run /api/table-headers (step 4) first"}), 400
            intent = ScrapeIntent.from_dict(sess["intent"])
            if sess.get("plans"):
                plans = [ScrapePlan.from_dict(p) for p in sess["plans"]]
            else:
                plans = [ScrapePlan.from_dict(p) for p in [sess["plan"]]]
            job = ScrapeJob(
                job_id=intent.job_id,
                intent=intent,
                plans=plans,
                plan=plans[0],
                status="ready",
                table_schema=sess.get("table_schema"),
            )
            live = bool(body.get("live"))
            result = universal_service.trigger_scrape_all(plans, job, max_pages=scrape_max, live=live)
            if live and result.get("started"):
                sess["keep_live"] = True
                sess = save_session(get_user_id(request), sess)
            elif live and not result.get("started"):
                sess["keep_live"] = False
                sess = save_session(get_user_id(request), sess)
            msg = (
                f"Live scrape watching {len(plans)} sources"
                if live and result.get("started")
                else f"Universal scrape started for {len(plans)} sources"
            )
            return jsonify(
                {
                    "ok": True,
                    "message": msg,
                    **result,
                    "job_id": job.job_id,
                    "session": _public_session(sess),
                }
            )
        elif body.get("prompt"):
            scrape_max = int(max_pages_raw or os.getenv("SCRAPE_MAX_PAGES", "3"))
            job = run_pipeline(body["prompt"], max_pages=scrape_max)
            return jsonify({"ok": True, "started": True, "job": job.to_dict()})
        else:
            return jsonify({"ok": False, "error": "Inspect a source or pass prompt / use_egazette_preset"}), 400
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)
