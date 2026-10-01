import base64
import json
import logging
import os
import jwt

def get_user_id(req) -> str:
    # 1. Check for X-User-Id header passed by trusted frontend proxy (Cloudflare Pages)
    x_user = req.headers.get("X-User-Id")
    if x_user:
        return x_user.strip()

    auth = req.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return "anonymous"
    token = auth.split(" ")[1]
    
    secret = os.getenv("SUPABASE_JWT_SECRET")
    try:
        if secret:
            try:
                header = jwt.get_unverified_header(token)
                alg = header.get("alg", "HS256")
                payload = jwt.decode(
                    token,
                    secret,
                    algorithms=[alg, "HS256", "HS384", "HS512", "RS256", "ES256"],
                    options={"verify_aud": False, "verify_signature": True},
                )
                return payload.get("sub", "anonymous")
            except Exception as sig_err:
                logging.warning(f"JWT signature verification failed ({sig_err}). Falling back to unverified payload decode.")
                payload = jwt.decode(token, options={"verify_signature": False})
                return payload.get("sub", "anonymous")
        else:
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload.get("sub", "anonymous")
    except Exception as e:
        logging.error(f"Unexpected error decoding JWT: {e}")
        return "anonymous"
