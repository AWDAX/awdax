import hmac
import logging
import os

import jwt


class AuthError(Exception):
    """A token was presented but could not be trusted. Answered as 401, never mapped to a shared user."""


_SIGN_IN_MESSAGE = "Your sign-in could not be verified. Reload the page and sign in again."

# One warning per process when running without PROXY_SHARED_SECRET (tests reset this).
_warned_unverified = False


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


def _verified_subject(token: str, secret: str) -> str:
    # Only HS256/384/512 project secrets can be checked here. This project's tokens are ES256, which the
    # proxy verifies against Supabase's keys and then vouches for with X-User-Id + X-Proxy-Secret.
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256", "HS384", "HS512"], options={"verify_aud": False})
    except Exception as exc:
        logging.warning("JWT rejected: %s", type(exc).__name__)
        raise AuthError(_SIGN_IN_MESSAGE) from exc
    sub = payload.get("sub")
    if not sub:
        raise AuthError(_SIGN_IN_MESSAGE)
    return str(sub)


def _get_user_id_strict(req, proxy_secret: str) -> str:
    """PROXY_SHARED_SECRET is set (production): identity is proven or the request is refused."""
    x_user = (req.headers.get("X-User-Id") or "").strip()
    if x_user:
        # A user header from anyone but the proxy is a forgery attempt; never fall back to the token path.
        if _proxy_secret_matches(req, proxy_secret):
            return x_user
        logging.warning("X-User-Id rejected: missing or wrong X-Proxy-Secret")
        raise AuthError(_SIGN_IN_MESSAGE)
    token = _bearer_token(req)
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if not token or not jwt_secret:
        raise AuthError(_SIGN_IN_MESSAGE)
    return _verified_subject(token, jwt_secret)


def _get_user_id_permissive(req) -> str:
    """Local development, no PROXY_SHARED_SECRET: today's behaviour. Identity here is NOT verified."""
    global _warned_unverified
    if not _warned_unverified:
        _warned_unverified = True
        logging.warning(
            "PROXY_SHARED_SECRET is not set: user identity (X-User-Id or an unverified token) is unverified. "
            "Set PROXY_SHARED_SECRET (the same value on Pages) in production."
        )
    x_user = req.headers.get("X-User-Id")
    if x_user:
        return x_user.strip()

    token = _bearer_token(req)
    if not token:
        return "anonymous"

    secret = os.getenv("SUPABASE_JWT_SECRET")
    if secret:
        return _verified_subject(token, secret)
    try:
        # Local dev without the proxy: read the user id without verifying the signature.
        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:
        logging.warning("JWT rejected: %s", type(exc).__name__)
        raise AuthError(_SIGN_IN_MESSAGE) from exc
    sub = payload.get("sub")
    if not sub:
        raise AuthError(_SIGN_IN_MESSAGE)
    return str(sub)


def get_user_id(req) -> str:
    proxy_secret = os.getenv("PROXY_SHARED_SECRET")
    if proxy_secret:
        return _get_user_id_strict(req, proxy_secret)
    return _get_user_id_permissive(req)
