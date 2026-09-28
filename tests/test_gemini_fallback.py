from google.genai import errors
from pydantic import BaseModel

import llm.gemini as gemini
from config.settings import settings


class _Out(BaseModel):
    ok: bool


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text


class _Models:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes, self.calls = outcomes, []

    def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        out = self.outcomes[model]
        if isinstance(out, Exception):
            raise out
        return _Response(out)


class _Client:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.models = _Models(outcomes)


def _run(outcomes: dict[str, object]):
    """generate_json against a fake client, trying the models in the order given."""
    client = _Client(outcomes)
    original = gemini._client, gemini._candidate_models
    gemini._client, gemini._candidate_models = (lambda: client), (lambda: list(outcomes))
    try:
        return gemini.generate_json("prompt", _Out), client.models.calls
    except gemini.GeminiError as exc:
        return exc, client.models.calls
    finally:
        gemini._client, gemini._candidate_models = original


def _error(kind, code: int, status: str):
    return kind(code, {"error": {"code": code, "message": f"{status} test", "status": status}})


OK = '{"ok": true}'


def test_overloaded_model_falls_back_to_the_next():
    result, calls = _run({"a": _error(errors.ServerError, 503, "UNAVAILABLE"), "b": OK})
    assert result == _Out(ok=True)
    assert calls == ["a", "b"]


def test_quota_and_retired_models_also_fall_back():
    result, calls = _run({
        "a": _error(errors.ClientError, 429, "RESOURCE_EXHAUSTED"),
        "b": _error(errors.ClientError, 404, "NOT_FOUND"),
        "c": OK,
    })
    assert result == _Out(ok=True)
    assert calls == ["a", "b", "c"]


def test_bad_request_is_not_retried_on_other_models():
    result, calls = _run({"a": _error(errors.ClientError, 400, "INVALID_ARGUMENT"), "b": OK})
    assert isinstance(result, gemini.GeminiError)
    assert calls == ["a"]


def test_every_model_down_raises_the_last_error():
    result, calls = _run({"a": _error(errors.ServerError, 503, "UNAVAILABLE"), "b": _error(errors.ServerError, 500, "INTERNAL")})
    assert isinstance(result, gemini.GeminiError) and "500" in str(result)
    assert calls == ["a", "b"]


def test_configured_model_first_then_fallbacks_without_repeats():
    original = settings.gemini_model, settings.gemini_fallback_models
    object.__setattr__(settings, "gemini_model", "m2")
    object.__setattr__(settings, "gemini_fallback_models", ("m1", "m2", "m3"))
    try:
        assert gemini._candidate_models() == ["m2", "m1", "m3"]
    finally:
        object.__setattr__(settings, "gemini_model", original[0])
        object.__setattr__(settings, "gemini_fallback_models", original[1])
