"""Who is calling: an API key, a Supabase token the backend verifies itself, or (local development only) a trusted identity.

Strict by default: anything that cannot be proven is a 401, never a shared "anonymous" user. See docs/CONFIGURATION.md.
"""

import hmac
import logging
import os
from dataclasses import dataclass

import jwt


class AuthError(Exception):
    """A token was presented but could not be trusted. Answered as 401, never mapped to a shared user."""


_SIGN_IN_MESSAGE = "Your sign-in could not be verified. Reload the page and sign in again."

API_KEY_PREFIX = "awx_"
FULL_ACCESS = frozenset({"read", "write"})
_HS_ALGS = ["HS256", "HS384", "HS512"]
_ASYM_ALGS = ["ES256", "RS256"]

# One warning per process when running in dev mode (tests reset this).
_warned_unverified = False

# One JWKS client per Supabase URL, so the signing keys are fetched once rather than on every request.
_jwks_clients: dict[str, "jwt.PyJWKClient"] = {}


@dataclass(frozen=True)
class Identity:
    """Who a request is, and how that was proven: api_key | proxy | jwt | dev."""

    user_id: str
    method: str
    scopes: frozenset = FULL_ACCESS
    key_id: str = ""  # the API key behind an api_key identity (for rate limits and audit), else ""


def _dev_mode() -> bool:
    """Strict is the default. Only an explicit AWDAX_AUTH_MODE=dev (local development, `npm run dev:agent`) trusts
    unverified identity."""
    return (os.getenv("AWDAX_AUTH_MODE") or "").strip().lower() == "dev"


def _clean_user_id(value: object) -> str:
    uid = str(value or "").strip()
    if not uid or uid == "anonymous" or len(uid) > 128:
        raise AuthError(_SIGN_IN_MESSAGE)
    return uid


def _proxy_secret_matches(req, expected: str) -> bool:
    given = req.headers.get("X-Proxy-Secret") or ""
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def _bearer_token(req) -> str | None:
    auth = req.headers.get("Authorization") or ""
    if auth.startswith("Bearer ") and auth[7:].strip():
        return auth[7:].strip()
    # EventSource and WebSocket can't send headers; the app puts the same token in this /api cookie
    # (Frontend/src/api/client.ts setStreamToken).
    return req.cookies.get("awdax_token") or None


def _api_key(req) -> str | None:
    """An AWDAX API key from `Authorization: Bearer awx_...` or `X-API-Key: awx_...`."""
    auth = req.headers.get("Authorization") or ""
    if auth.startswith("Bearer ") and auth[7:].strip().startswith(API_KEY_PREFIX):
        return auth[7:].strip()
    key = (req.headers.get("X-API-Key") or "").strip()
    return key if key.startswith(API_KEY_PREFIX) else None


def _identity_from_api_key(key: str, *, dev: bool = False) -> Identity:
    try:
        import api_keys
    except ImportError as exc:  # keys not installed: a key can never be proven
        raise AuthError(_SIGN_IN_MESSAGE) from exc
    resolved = api_keys.resolve_key(key)
    if not resolved:
        raise AuthError("This API key is not valid or has been revoked.")
    # In dev mode the "account" may be the shared dev user; in strict mode a key must belong to a real one.
    owner = str(resolved.user_id).strip() if dev else _clean_user_id(resolved.user_id)
    if not owner:
        raise AuthError(_SIGN_IN_MESSAGE)
    return Identity(owner, "api_key", frozenset(resolved.scopes), resolved.key_id)


def _signed_in_subject(payload: dict) -> str:
    """The `sub` of a Google sign-in. Google is the app's only sign-in; anonymous or email/password accounts can be
    created with the public key, so accepting them would hand anyone unlimited identities and get round per-user limits."""
    meta = payload.get("app_metadata") or {}
    providers = meta.get("providers") if isinstance(meta.get("providers"), list) else [meta.get("provider")]
    if payload.get("is_anonymous") is True or "google" not in providers:
        logging.warning("JWT rejected: not a Google sign-in")
        raise AuthError(_SIGN_IN_MESSAGE)
    return _clean_user_id(payload.get("sub"))


def _hs_subject(token: str, secret: str) -> str:
    try:
        payload = jwt.decode(token, secret, algorithms=_HS_ALGS, options={"verify_aud": False})
    except Exception as exc:
        logging.warning("JWT rejected: %s", type(exc).__name__)
        raise AuthError(_SIGN_IN_MESSAGE) from exc
    return _signed_in_subject(payload)


def _jwks_client(supabase_url: str) -> "jwt.PyJWKClient":
    client = _jwks_clients.get(supabase_url)
    if client is None:
        client = _jwks_clients[supabase_url] = jwt.PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True)
    return client


def _asymmetric_subject(token: str) -> str:
    """ES256/RS256 tokens (this project's Supabase tokens) checked against Supabase's published signing keys."""
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    if not supabase_url:
        logging.warning("JWT rejected: SUPABASE_URL is not set on the backend")
        raise AuthError(_SIGN_IN_MESSAGE)
    try:
        key = _jwks_client(supabase_url).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            key.key,
            algorithms=_ASYM_ALGS,
            audience="authenticated",
            issuer=f"{supabase_url}/auth/v1",
            leeway=30,
            options={"require": ["exp", "sub"]},
        )
    except Exception as exc:
        logging.warning("JWT rejected: %s", type(exc).__name__)
        raise AuthError(_SIGN_IN_MESSAGE) from exc
    return _signed_in_subject(payload)


def _verified_subject(token: str) -> str:
    """The `sub` of a token whose signature has been checked. The algorithm in the header only picks which key to
    check against (an unsigned `none` token matches neither); the signature must still verify."""
    try:
        alg = str(jwt.get_unverified_header(token).get("alg") or "")
    except Exception as exc:
        logging.warning("JWT rejected: %s", type(exc).__name__)
        raise AuthError(_SIGN_IN_MESSAGE) from exc
    if alg in _HS_ALGS:
        secret = os.getenv("SUPABASE_JWT_SECRET")
        if not secret:
            raise AuthError(_SIGN_IN_MESSAGE)
        return _hs_subject(token, secret)
    if alg in _ASYM_ALGS:
        return _asymmetric_subject(token)
    logging.warning("JWT rejected: unsupported alg %r", alg)
    raise AuthError(_SIGN_IN_MESSAGE)


def _identity_strict(req) -> Identity:
    """Identity is proven or the request is refused. Never 'anonymous', never a header taken on trust."""
    x_user = req.headers.get("X-User-Id")
    if x_user is not None:
        # A user header from anyone but the proxy is a forgery attempt; never fall back to the token path.
        proxy_secret = os.getenv("PROXY_SHARED_SECRET")
        if proxy_secret and _proxy_secret_matches(req, proxy_secret):
            return Identity(_clean_user_id(x_user), "proxy")
        logging.warning("X-User-Id rejected: missing or wrong X-Proxy-Secret")
        raise AuthError(_SIGN_IN_MESSAGE)

    token = _bearer_token(req)
    if not token:
        raise AuthError(_SIGN_IN_MESSAGE)
    return Identity(_verified_subject(token), "jwt")


def _identity_dev(req) -> Identity:
    """AWDAX_AUTH_MODE=dev: today's permissive behaviour. Identity here is NOT verified. Local use only."""
    global _warned_unverified
    if not _warned_unverified:
        _warned_unverified = True
        logging.warning(
            "AWDAX_AUTH_MODE=dev: user identity (X-User-Id or an unverified token) is unverified. "
            "Remove it (strict is the default) and set SUPABASE_URL so sign-in is verified in production."
        )
    x_user = (req.headers.get("X-User-Id") or "").strip()
    if x_user:
        return Identity(x_user, "dev")

    token = _bearer_token(req)
    if not token:
        return Identity("anonymous", "dev")

    secret = os.getenv("SUPABASE_JWT_SECRET")
    if secret:
        return Identity(_hs_subject(token, secret), "dev")
    try:
        # Local dev without the proxy: read the user id without verifying the signature.
        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:
        logging.warning("JWT rejected: %s", type(exc).__name__)
        raise AuthError(_SIGN_IN_MESSAGE) from exc
    sub = str(payload.get("sub") or "").strip()
    if not sub:
        raise AuthError(_SIGN_IN_MESSAGE)
    return Identity(sub, "dev")


def get_identity(req) -> Identity:
    """Who the request is. Within one Flask request the answer is worked out once (the token or key is checked once)."""
    try:
        from flask import g, has_request_context, request as flask_request

        shared = has_request_context() and req is flask_request
    except ImportError:  # no Flask: only the tests of this module
        shared = False
    if shared:
        cached = getattr(g, "awdax_identity", None)
        if cached is not None:
            return cached
    # An API key means the same in both modes; everything else is proven (strict) or taken as it comes (dev).
    key = _api_key(req)
    if key:
        identity = _identity_from_api_key(key, dev=_dev_mode())
    else:
        identity = _identity_dev(req) if _dev_mode() else _identity_strict(req)
    if shared:
        g.awdax_identity = identity
    return identity


def get_user_id(req) -> str:
    return get_identity(req).user_id
