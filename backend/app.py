"""Flask application entrypoint."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask

from .auth import init_auth
from .datastore import DataStore
from .routes.admin import register_admin_routes
from .routes.api import register_api_routes
from .routes.pages import register_page_routes

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config["SECRET_KEY"] = os.environ.get("USACO_RATING_SECRET", secrets.token_hex(16))

    datastore = DataStore()
    app.config["DATASTORE"] = datastore

    init_auth(app)
    register_page_routes(app)
    register_admin_routes(app)
    register_api_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
