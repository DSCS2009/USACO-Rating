"""Dependency helpers for retrieving shared services."""

from __future__ import annotations

from flask import current_app

from .datastore import DataStore


def get_datastore() -> DataStore:
    datastore = current_app.config.get("DATASTORE")
    if datastore is None:
        raise RuntimeError("DataStore has not been initialised on the Flask app")
    return datastore
