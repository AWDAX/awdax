from __future__ import annotations

from flask import jsonify


def detail_response(status: int, detail: str):
    return jsonify({"detail": detail}), status
