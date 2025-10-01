#!/usr/bin/env python3
"""Remove non-custom courses and related data."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.datastore import DataStore  # type: ignore

DATA_DIR = ROOT / "backend" / "data"
STORE_PATH = DATA_DIR / "store.json"
TYPES_PATH = DATA_DIR / "types.json"
PROBLEMS_PATH = DATA_DIR / "problems.json"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return default
    return json.loads(text)


def _save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalise_type_ids(entries: Iterable[Dict[str, Any]]) -> Set[int]:
    result: Set[int] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_id = entry.get("id")
        try:
            type_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if type_id > 0:
            result.add(type_id)
    return result


def _filter_custom_problems(store: Dict[str, Any], custom_type_ids: Set[int]) -> tuple[Set[int], int]:
    problems = store.get("custom_problems", []) or []
    kept: List[Dict[str, Any]] = []
    problem_ids: Set[int] = set()
    for problem in problems:
        if not isinstance(problem, dict):
            continue
        try:
            problem_type = int(problem.get("type", 0) or 0)
            problem_id = int(problem.get("id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if problem_type in custom_type_ids and problem_id > 0:
            kept.append(problem)
            problem_ids.add(problem_id)
    store["custom_problems"] = kept
    removed = len(problems) - len(kept)
    return problem_ids, removed


def _filter_votes(store: Dict[str, Any], valid_problem_ids: Set[int]) -> tuple[Set[int], int]:
    votes = store.get("votes", []) or []
    kept: List[Dict[str, Any]] = []
    vote_ids: Set[int] = set()
    for vote in votes:
        if not isinstance(vote, dict):
            continue
        try:
            problem_id = int(vote.get("problem_id", 0) or 0)
            vote_id = int(vote.get("id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if problem_id in valid_problem_ids and vote_id > 0:
            kept.append(vote)
            vote_ids.add(vote_id)
    store["votes"] = kept
    removed = len(votes) - len(kept)
    return vote_ids, removed


def _filter_reports(store: Dict[str, Any], valid_vote_ids: Set[int]) -> int:
    reports = store.get("reports", []) or []
    kept: List[Dict[str, Any]] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        try:
            vote_id = int(report.get("vote_id", 0) or 0)
        except (TypeError, ValueError):
            vote_id = 0
        if vote_id and vote_id in valid_vote_ids:
            kept.append(report)
    store["reports"] = kept
    return len(reports) - len(kept)


def _filter_overrides(store: Dict[str, Any], valid_problem_ids: Set[int]) -> None:
    overrides = store.get("problem_overrides", {}) or {}
    filtered: Dict[str, Any] = {}
    for key, payload in overrides.items():
        try:
            problem_id = int(key)
        except (TypeError, ValueError):
            continue
        if problem_id in valid_problem_ids:
            filtered[str(problem_id)] = payload
    store["problem_overrides"] = filtered


def _filter_course_mappings(store: Dict[str, Any], custom_type_ids: Set[int]) -> None:
    contests = store.get("course_contests", {}) or {}
    store["course_contests"] = {
        str(type_id): contests.get(str(type_id), [])
        for type_id in custom_type_ids
        if str(type_id) in contests
    }

    type_categories = store.get("type_categories", {}) or {}
    filtered_categories: Dict[str, List[int]] = {}
    referenced_category_ids: Set[int] = set()
    for raw_type_id, raw_category_ids in type_categories.items():
        try:
            type_id = int(raw_type_id)
        except (TypeError, ValueError):
            continue
        if type_id not in custom_type_ids:
            continue
        clean_ids: List[int] = []
        for raw_category_id in raw_category_ids or []:
            try:
                category_id = int(raw_category_id)
            except (TypeError, ValueError):
                continue
            clean_ids.append(category_id)
            referenced_category_ids.add(category_id)
        filtered_categories[str(type_id)] = clean_ids
    store["type_categories"] = filtered_categories

    categories = store.get("course_categories", []) or []
    store["course_categories"] = [
        category
        for category in categories
        if isinstance(category, dict) and category.get("id") in referenced_category_ids
    ]


def _reset_defaults(store: Dict[str, Any], custom_type_ids: Set[int]) -> None:
    global_default = store.get("global_default_course_id")
    try:
        global_default_id = int(global_default) if global_default is not None else None
    except (TypeError, ValueError):
        global_default_id = None
    if not global_default_id or global_default_id not in custom_type_ids:
        store["global_default_course_id"] = None
    for user in store.get("users", []) or []:
        if not isinstance(user, dict):
            continue
        try:
            default_course = int(user.get("default_course_id", 0) or 0)
        except (TypeError, ValueError):
            default_course = 0
        if default_course not in custom_type_ids:
            user["default_course_id"] = None


def _filter_types_file(custom_type_ids: Set[int]) -> None:
    payload = _load_json(TYPES_PATH, {"types": [], "groups": []})
    filtered_types = [
        entry
        for entry in payload.get("types", []) or []
        if isinstance(entry, dict) and entry.get("id") in custom_type_ids
    ]
    _save_json(TYPES_PATH, {"types": filtered_types, "groups": []})


def _filter_problems_file(custom_type_ids: Set[int]) -> None:
    payload = _load_json(PROBLEMS_PATH, {})
    filtered: Dict[str, Any] = {}
    for raw_type_id, info in (payload or {}).items():
        try:
            type_id = int(raw_type_id)
        except (TypeError, ValueError):
            continue
        if type_id not in custom_type_ids:
            continue
        filtered[str(type_id)] = info
    _save_json(PROBLEMS_PATH, filtered)


def main() -> None:
    if not STORE_PATH.exists():
        raise SystemExit("store.json not found")
    store = _load_json(STORE_PATH, {})
    custom_type_ids = _normalise_type_ids(store.get("custom_types", []) or [])

    problem_ids, removed_problems = _filter_custom_problems(store, custom_type_ids)
    vote_ids, removed_votes = _filter_votes(store, problem_ids)
    removed_reports = _filter_reports(store, vote_ids)
    _filter_overrides(store, problem_ids)
    _filter_course_mappings(store, custom_type_ids)
    _reset_defaults(store, custom_type_ids)

    _save_json(STORE_PATH, store)

    _filter_types_file(custom_type_ids)
    _filter_problems_file(custom_type_ids)

    datastore = DataStore()
    datastore._rebuild_problem_stats()
    datastore._save_store()

    remaining = sorted(custom_type_ids) if custom_type_ids else []
    print("Removed problems:", removed_problems)
    print("Removed votes:", removed_votes)
    print("Removed reports:", removed_reports)
    print("Remaining custom course IDs:", remaining)


if __name__ == "__main__":
    main()
