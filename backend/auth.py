"""Authentication and authorisation helpers."""

from __future__ import annotations

import secrets
from typing import Any, Dict, Optional, Tuple

from flask import Flask, abort, g, session


def generate_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["_csrf_token"] = token
    return token


def validate_csrf(token: Optional[str]) -> bool:
    return bool(token) and token == session.get("_csrf_token")


def get_active_user() -> Optional[Dict[str, Any]]:
    user = getattr(g, "user", None)
    if not user:
        return None
    if not user.get("approved") or user.get("banned"):
        return None
    return user


def require_login() -> Dict[str, Any]:
    user = getattr(g, "user", None)
    if not user:
        abort(401)
    return user


def require_admin() -> Dict[str, Any]:
    user = require_login()
    if not user.get("is_admin"):
        abort(403)
    return user


def api_user_guard() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    user = getattr(g, "user", None)
    if not user:
        return None, {"error": "Not logged in"}
    if not user.get("approved"):
        return None, {"error": "Account pending approval"}
    if user.get("banned"):
        return None, {"error": "Account banned"}
    return user, None


def init_auth(app: Flask) -> None:
    """Register session hooks and context processors on the app."""

    datastore = app.config["DATASTORE"]

    @app.before_request
    def load_current_user() -> None:
        user_id = session.get("user_id")
        g.user = datastore.find_user_by_id(user_id) if user_id else None
        if g.user and g.user.get("banned"):
            session.pop("user_id", None)
            g.user = None

    @app.context_processor
    def inject_globals() -> Dict[str, Any]:
        return {"csrf_token": generate_csrf_token}
