import httpx
from pydantic import BaseModel

import llm.gemini as gemini
from config.settings import settings
from llm import nvidia


class _Out(BaseModel):
    ok: bool


def _with_settings(**values):
    original = {k: getattr(settings, k) for k in values}
    for k, v in values.items():
        object.__setattr__(settings, k, v)
    return lambda: [object.__setattr__(settings, k, v) for k, v in original.items()]


def _route(nvidia_outcomes: dict[str, object], *, key="nvapi-test"):
    """Run gemini.generate_json with fake NVIDIA models and a fake Gemini; return (result, calls)."""
    calls: list[str] = []

    def fake_nvidia(model, prompt, schema, *, temperature):
        calls.append(model)
        out = nvidia_outcomes[model]
        if isinstance(out, Exception):
            raise out
        return out

    def fake_gemini(prompt, schema, temperature):
        calls.append("gemini")
        return _Out(ok=False)

    restore = _with_settings(nvidia_api_key=key, nvidia_models=tuple(nvidia_outcomes))
    original = gemini.nvidia.generate_json, gemini._gemini_json
    gemini.nvidia.generate_json, gemini._gemini_json = fake_nvidia, fake_gemini
    try:
        return gemini.generate_json("p", _Out), calls
    finally:
        gemini.nvidia.generate_json, gemini._gemini_json = original
        restore()


def test_nvidia_answers_first():
    result, calls = _route({"n1": _Out(ok=True), "n2": _Out(ok=True)})
    assert result == _Out(ok=True) and calls == ["n1"]


def test_next_nvidia_model_then_gemini_when_nvidia_is_busy():
    result, calls = _route({"n1": nvidia.NvidiaError("429"), "n2": nvidia.NvidiaError("503")})
    assert result == _Out(ok=False) and calls == ["n1", "n2", "gemini"]


def test_refused_key_goes_straight_to_gemini_and_stays_skipped():
    gemini._nvidia_key_rejected = False
    try:
        result, calls = _route({"n1": nvidia.NvidiaError("401", key_rejected=True), "n2": _Out(ok=True)})
        assert calls == ["n1", "gemini"]
        _, calls = _route({"n1": _Out(ok=True)})
        assert calls == ["gemini"]  # a refused key isn't retried on every call
    finally:
        gemini._nvidia_key_rejected = False


def test_without_a_key_only_gemini_is_used():
    _, calls = _route({"n1": _Out(ok=True)}, key=None)
    assert calls == ["gemini"]


def test_json_text_drops_reasoning_and_fences():
    reply = '<think>They want JSON.</think>\n```json\n{"ok": true}\n```'
    assert _Out.model_validate_json(nvidia.json_text(reply)) == _Out(ok=True)


def test_chat_retries_without_response_format_when_refused():
    bodies: list[dict] = []

    def fake_post(model, body):
        bodies.append(dict(body))
        if "response_format" in body:
            return httpx.Response(400, text="response_format not supported")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    original = nvidia._post
    nvidia._post = fake_post
    restore = _with_settings(nvidia_api_key="nvapi-test")
    try:
        assert nvidia.generate_json("m", "p", _Out, temperature=0.1) == _Out(ok=True)
    finally:
        nvidia._post = original
        restore()
    assert "response_format" in bodies[0] and "response_format" not in bodies[1]
    assert '"ok"' in bodies[1]["messages"][0]["content"]  # the schema travels in the prompt too


def test_chat_marks_a_refused_key():
    original = nvidia._post
    nvidia._post = lambda model, body: httpx.Response(401, text="Unauthorized")
    try:
        nvidia.chat("m", [{"role": "user", "content": "hi"}], temperature=0.1)
        raise AssertionError("expected NvidiaError")
    except nvidia.NvidiaError as exc:
        assert exc.key_rejected
    finally:
        nvidia._post = original
