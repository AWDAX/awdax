import hmac
import logging
import os

import jwt


class AuthError(Exception):
    """A token was presented but could not be trusted. Answered as 401, never mapped to a shared user."""


def _proxy_trusted(req) -> bool:
    """X-User-Id is honoured only from the trusted proxy: no secret configured (local dev) or matching secret."""
    expected = os.getenv("PROXY_SHARED_SECRET")
    if not expected:
        return True
    given = req.headers.get("X-Proxy-Secret") or ""
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def _bearer_token(req) -> str | None:
    auth = req.headers.get("Authorization") or ""
    if auth.startswith("Bearer ") and auth[7:].strip():
        return auth[7:].strip()
    # EventSource and WebSocket can't send headers; the app puts the same token in this /api cookie
    # (Frontend/src/api/client.ts setStreamToken).
    return req.cookies.get("awdax_token") or None


def get_user_id(req) -> str:
    # 1. X-User-Id passed by the trusted frontend proxy (Cloudflare Pages)
    x_user = req.headers.get("X-User-Id")
    if x_user and _proxy_trusted(req):
        return x_user.strip()

    token = _bearer_token(req)
    if not token:
        return "anonymous"

    secret = os.getenv("SUPABASE_JWT_SECRET")
    try:
        if secret:
            # Only HS256 project secrets can be checked here. This project's tokens are ES256, so leave
            # SUPABASE_JWT_SECRET unset and rely on the proxy (it verifies ES256 against Supabase's keys).
            payload = jwt.decode(token, secret, algorithms=["HS256", "HS384", "HS512"], options={"verify_aud": False})
        else:
            # Local dev without the proxy: read the user id without verifying the signature.
            payload = jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:
        logging.warning("JWT rejected: %s", type(exc).__name__)
        raise AuthError("Your sign-in could not be verified. Reload the page and sign in again.") from exc
    sub = payload.get("sub")
    if not sub:
        raise AuthError("Your sign-in could not be verified. Reload the page and sign in again.")
    return str(sub)
