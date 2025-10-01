"""Data access layer for USACO Rating app."""

from __future__ import annotations

import json
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROBLEMS_PATH = DATA_DIR / "problems.json"
TYPES_PATH = DATA_DIR / "types.json"
STORE_PATH = DATA_DIR / "store.json"
ANNOUNCEMENTS_SEED_PATH = DATA_DIR / "announcements.json"

DEFAULT_TYPES_PAYLOAD: Dict[str, Any] = {"types": [], "groups": []}
DEFAULT_PROBLEMS_PAYLOAD: Dict[str, Any] = {}
DEFAULT_STORE_PAYLOAD: Dict[str, Any] = {
    "announcements": [],
    "reports": [],
    "next_report_id": 1,
    "problem_overrides": {},
    "custom_problems": [],
    "custom_types": [],
    "course_contests": {},
    "course_categories": [],
    "type_categories": {},
    "global_default_course_id": None,
    "next_problem_id": 1,
    "next_user_id": 1,
    "next_vote_id": 1,
    "next_contest_id": 1,
    "next_type_id": 1,
    "next_category_id": 1,
    "users": [],
    "votes": [],
}
DEFAULT_ANNOUNCEMENTS_SEED: Dict[str, Any] = {"announcements": []}

PROBLEM_STATS_SPECS = {
    "overall": {"avg": "avg_difficulty", "sd": "sd_difficulty", "cnt": "cnt1"},
    "thinking": {"avg": "avg_thinking", "sd": "sd_thinking", "cnt": "cnt_thinking"},
    "implementation": {"avg": "avg_implementation", "sd": "sd_implementation", "cnt": "cnt_implementation"},
    "quality": {"avg": "avg_quality", "sd": "sd_quality", "cnt": "cnt2"},
}


def _clone_default(payload: Any) -> Any:
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _now_ts() -> int:
    return int(time.time())


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _elo_win_probability(a: float, b: float) -> float:
    return 1.0 / (1 + 10 ** ((b - a) / 400.0))


def _calc_overall(thinking: float, implementation: float) -> float:
    left = 1.0
    right = 8000.0
    eps = 1e-4
    while right - left > eps:
        mid = (left + right) / 2
        if _elo_win_probability(mid, thinking) * _elo_win_probability(mid, implementation) > 0.5:
            right = mid
        else:
            left = mid
    return left


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2


class DataStore:
    def __init__(self) -> None:
        self._load_types()
        self._load_problems()
        self.custom_types: Dict[int, Dict[str, Any]] = {}
        self.course_categories: Dict[int, Dict[str, Any]] = {}
        self.type_categories: Dict[int, List[int]] = {}
        self._store_mtime: float = 0.0
        self._load_store()
        self._bootstrap_announcements()

    def _load_types(self) -> None:
        payload = self._load_json_file(TYPES_PATH, DEFAULT_TYPES_PAYLOAD)
        self.types = {item["id"]: item for item in payload["types"]}
        self.type_groups = []
        for group in payload.get("groups", []):
            entries = [self.types[tid] for tid in group.get("type_ids", []) if tid in self.types]
            if entries:
                self.type_groups.append({"label": group.get("label", ""), "entries": entries})

    def _load_problems(self) -> None:
        payload: Dict[str, Any] = self._load_json_file(PROBLEMS_PATH, DEFAULT_PROBLEMS_PAYLOAD)
        self.problems_by_type: Dict[int, Dict[str, Any]] = {}
        self.problem_map: Dict[int, Dict[str, Any]] = {}
        for type_key, info in payload.items():
            type_id = int(type_key)
            type_info = info.get("type", self.types.get(type_id, {"id": type_id, "name": ""}))
            problems = []
            for item in info.get("problems", []):
                item = dict(item)
                item["type"] = item.get("type", type_id)
                item.setdefault("setter", [])
                item.setdefault("source", [])
                item.setdefault("meta", {})
                self._init_problem_stats(item)
                self.problem_map[item["id"]] = item
                problems.append(item)
            self.problems_by_type[type_id] = {"type": type_info, "problems": problems}
        self.next_problem_id = max(self.problem_map.keys(), default=0) + 1

    def _load_store(self) -> None:
        self.store = self._load_json_file(STORE_PATH, DEFAULT_STORE_PAYLOAD)
        self.course_categories.clear()
        self.type_categories.clear()
        self.store.setdefault("announcements", [])
        self.store.setdefault("reports", [])
        self.store.setdefault("problem_overrides", {})
        self.store.setdefault("custom_problems", [])
        self.store.setdefault("custom_types", [])
        self.store.setdefault("course_contests", {})
        self.store.setdefault("course_categories", [])
        self.store.setdefault("type_categories", {})
        self.store.setdefault("next_problem_id", self.next_problem_id)
        self.store.setdefault("next_user_id", 1)
        self.store.setdefault("next_vote_id", 1)
        self.store.setdefault("next_contest_id", 1)
        self.store.setdefault("next_category_id", 1)
        self.store.setdefault("next_report_id", 1)
        self._load_custom_types_from_store()

        # Ensure custom problems are reloaded from disk without duplicating previous entries.
        existing_custom_ids = [pid for pid, problem in self.problem_map.items() if problem.get("is_custom")]
        for pid in existing_custom_ids:
            problem = self.problem_map.pop(pid, None)
            if not problem:
                continue
            bucket = self.problems_by_type.get(problem.get("type"))
            if bucket:
                bucket["problems"] = [item for item in bucket.get("problems", []) if item.get("id") != pid]

        votes = self.store.setdefault("votes", [])
        users = self.store.setdefault("users", [])
        for user in users:
            if "password" in user and not user.get("legacy_password_hash"):
                user["legacy_password_hash"] = user.pop("password")
            user.setdefault("password_hash", None)
            user.setdefault("legacy_password_hash", None)
            user.setdefault("approved", user.get("is_admin", False))
            user.setdefault("banned", False)
            user.setdefault("roles", [])
            user.setdefault("tag_permissions", [])
            user.setdefault("luoguid", "")
            user.setdefault("info", "")
            user.setdefault("created_at", _now_ts())
            user["default_course_id"] = self._normalise_course_id(user.get("default_course_id"))
            if user.get("is_admin") and "admin" not in user["roles"]:
                user["roles"].append("admin")
            # Ensure tag permissions are unique strings
            normalised_perms = []
            seen_perm = set()
            for perm in user.get("tag_permissions", []) or []:
                perm_str = str(perm).strip()
                if perm_str and perm_str not in seen_perm:
                    seen_perm.add(perm_str)
                    normalised_perms.append(perm_str)
            user["tag_permissions"] = normalised_perms
        # Normalise votes to include new metrics
        vote_owner_map: Dict[int, Optional[int]] = {}
        for vote in votes:
            thinking = vote.get("thinking")
            implementation = vote.get("implementation")
            overall = vote.get("overall")
            legacy_difficulty = vote.get("difficulty")
            if thinking is None and legacy_difficulty is not None:
                thinking = legacy_difficulty
            if implementation is None and legacy_difficulty is not None:
                implementation = legacy_difficulty
            if overall is None and thinking is not None and implementation is not None:
                overall = _calc_overall(float(thinking), float(implementation))
            elif overall is None:
                overall = legacy_difficulty
            vote["thinking"] = float(thinking) if thinking is not None else None
            vote["implementation"] = float(implementation) if implementation is not None else None
            vote["overall"] = float(overall) if overall is not None else None
            if vote.get("overall") is not None:
                vote["difficulty"] = vote["overall"]
            vote.setdefault("quality", None)
            vote.setdefault("comment", "")
            vote.setdefault("public", False)
            vote.setdefault("deleted", False)
            vote.setdefault("accepted", True)
            vote.setdefault("score", 0)
            vote.setdefault("created_at", vote.get("created_at", _now_ts()))
            vote.setdefault("updated_at", vote.get("updated_at", vote["created_at"]))
            try:
                vid = int(vote.get("id", 0) or 0)
            except (TypeError, ValueError):
                continue
            if vid <= 0:
                continue
            vote_owner_map[vid] = vote.get("user_id")

        reports = self.store.setdefault("reports", [])
        next_report_id = max(1, int(self.store.get("next_report_id", 1) or 1))
        seen_report_ids: Set[int] = set()
        seen_pairs: Set[Tuple[int, int]] = set()
        normalised_reports: List[Dict[str, Any]] = []
        for raw_report in reports:
            report = dict(raw_report)
            try:
                rid_val = int(report.get("id", 0) or 0)
            except (TypeError, ValueError):
                rid_val = 0
            if rid_val <= 0 or rid_val in seen_report_ids:
                rid_val = next_report_id
                next_report_id += 1
            report["id"] = rid_val
            seen_report_ids.add(rid_val)

            reporter_raw = report.get("user_id", report.get("reporter_id"))
            reporter_id = None
            if reporter_raw is not None:
                try:
                    reporter_id = int(reporter_raw)
                except (TypeError, ValueError):
                    reporter_id = None
            if reporter_id is not None and reporter_id <= 0:
                reporter_id = None
            report["user_id"] = reporter_id
            report["reporter_id"] = reporter_id

            try:
                vote_id = int(report.get("vote_id", 0) or 0)
            except (TypeError, ValueError):
                vote_id = 0
            report["vote_id"] = vote_id

            if report.get("target_user_id") is None and vote_id in vote_owner_map:
                report["target_user_id"] = vote_owner_map[vote_id]
            if report.get("target_user_id") is not None:
                try:
                    report["target_user_id"] = int(report.get("target_user_id") or 0) or None
                except (TypeError, ValueError):
                    report["target_user_id"] = None

            report.setdefault("created_at", _now_ts())

            if reporter_id is not None and vote_id:
                pair = (vote_id, reporter_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

            normalised_reports.append(report)

        if normalised_reports != reports:
            self.store["reports"] = normalised_reports

        max_report_id = max(seen_report_ids) if seen_report_ids else 0
        if next_report_id <= max_report_id:
            next_report_id = max_report_id + 1
        self.store["next_report_id"] = max(self.store.get("next_report_id", 1), next_report_id)

        raw_global_default = self.store.get("global_default_course_id")
        if raw_global_default is None and "global_default_course_id" not in self.store:
            self.store["global_default_course_id"] = None
        else:
            self.store["global_default_course_id"] = self._normalise_course_id(raw_global_default)
        if self.store["next_problem_id"] < self.next_problem_id:
            self.store["next_problem_id"] = self.next_problem_id

        # Load category information --------------------------------------
        normalised_categories: List[Dict[str, Any]] = []
        max_category_id = 0
        for raw_category in self.store.get("course_categories", []):
            try:
                category_id = int(raw_category.get("id", 0) or 0)
            except (TypeError, ValueError):
                continue
            name = str(raw_category.get("name", "")).strip()
            if not category_id or not name:
                continue
            entry = {"id": category_id, "name": name}
            normalised_categories.append(entry)
            self.course_categories[category_id] = entry
            if category_id > max_category_id:
                max_category_id = category_id
        normalised_categories.sort(key=lambda item: item["id"])
        self.store["course_categories"] = normalised_categories
        next_category_candidate = max_category_id + 1
        if self.store.get("next_category_id", 0) < next_category_candidate:
            self.store["next_category_id"] = next_category_candidate

        normalised_type_categories: Dict[str, List[int]] = {}
        raw_type_categories = self.store.get("type_categories", {}) or {}
        for raw_type_id, raw_category_ids in raw_type_categories.items():
            try:
                type_id = int(raw_type_id)
            except (TypeError, ValueError):
                continue
            if type_id not in self.types:
                continue
            normalised_ids = []
            seen = set()
            for raw_category_id in raw_category_ids or []:
                try:
                    category_id = int(raw_category_id)
                except (TypeError, ValueError):
                    continue
                if category_id not in self.course_categories or category_id in seen:
                    continue
                seen.add(category_id)
                normalised_ids.append(category_id)
            if normalised_ids:
                normalised_type_categories[str(type_id)] = normalised_ids
                self.type_categories[type_id] = normalised_ids
        self.store["type_categories"] = normalised_type_categories

        contests_map = {}
        raw_map = self.store.get("course_contests", {}) or {}
        for course_id, contests in raw_map.items():
            try:
                key = str(int(course_id))
            except (TypeError, ValueError):
                continue
            bucket: List[Dict[str, Any]] = []
            for contest in contests or []:
                contest_id = int(contest.get("id", 0) or 0)
                name = str(contest.get("name", "")).strip()
                if not contest_id or not name:
                    continue
                bucket.append({"id": contest_id, "name": name})
            contests_map[key] = bucket
        self.store["course_contests"] = contests_map

        for raw in self.store.get("custom_problems", []):
            problem = dict(raw)
            problem.setdefault("meta", {})
            problem.setdefault("setter", [])
            problem.setdefault("source", [])
            problem["is_custom"] = True
            self._init_problem_stats(problem)
            self.problem_map[problem["id"]] = problem
            bucket = self.problems_by_type.setdefault(problem["type"], {"type": self.types.get(problem["type"], {"id": problem["type"], "name": ""}), "problems": []})
            bucket["problems"].append(problem)
        for pid, override in self.store.get("problem_overrides", {}).items():
            problem = self.problem_map.get(int(pid))
            if problem:
                problem.update(override)
        self._rebuild_problem_stats()
        self._store_mtime = self._store_file_mtime()

    def _load_custom_types_from_store(self) -> None:
        previous_custom_ids = set(getattr(self, "custom_types", {}).keys())
        for type_id in previous_custom_ids:
            self.types.pop(type_id, None)
            self.problems_by_type.pop(type_id, None)
        self.custom_types = {}
        existing_type_ids = list(self.types.keys())
        raw_custom_types = self.store.setdefault("custom_types", []) or []
        normalised_custom_types: List[Dict[str, Any]] = []
        for raw_type in raw_custom_types:
            try:
                type_id = int(raw_type.get("id", 0) or 0)
            except (TypeError, ValueError):
                continue
            name = str(raw_type.get("name", "")).strip()
            if not type_id or not name:
                continue
            entry = {"id": type_id, "name": name}
            normalised_custom_types.append(entry)
            self.types[type_id] = entry
            self.custom_types[type_id] = entry
            self.problems_by_type.setdefault(
                type_id,
                {"type": entry, "problems": []},
            )
            existing_type_ids.append(type_id)
        self.store["custom_types"] = normalised_custom_types
        proposed_next_type = max(existing_type_ids or [0]) + 1
        if self.store.get("next_type_id", 0) < proposed_next_type:
            self.store["next_type_id"] = proposed_next_type

    def _bootstrap_announcements(self) -> None:
        if self.store["announcements"]:
            existing_ids = [item.get("id", 0) for item in self.store["announcements"]]
            self.store.setdefault("next_announcement_id", max(existing_ids, default=0) + 1)
            return
        seed = self._load_json_file(ANNOUNCEMENTS_SEED_PATH, DEFAULT_ANNOUNCEMENTS_SEED)
        announcements = []
        for idx, item in enumerate(seed.get("announcements", []), start=1):
            ts = self._parse_time_string(item.get("time"))
            announcements.append({
                "id": idx,
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "pinned": bool(item.get("pinned")),
                "created_at": ts,
            })
        self.store["announcements"] = announcements
        self.store["next_announcement_id"] = len(announcements) + 1
        self._save_store()

    def _load_json_file(self, path: Path, default_payload: Any) -> Any:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            data = _clone_default(default_payload)
            path.write_text(json.dumps(default_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        text = text.strip()
        if not text:
            data = _clone_default(default_payload)
            path.write_text(json.dumps(default_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            data = _clone_default(default_payload)
            path.write_text(json.dumps(default_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return data

    def _init_problem_stats(self, item: Dict[str, Any]) -> None:
        stats: Dict[str, Dict[str, float]] = {}
        for metric, mapping in PROBLEM_STATS_SPECS.items():
            cnt_key = mapping["cnt"]
            avg_key = mapping["avg"]
            sd_key = mapping["sd"]
            count = int(item.get(cnt_key) or 0)
            avg_raw = item.get(avg_key)
            avg = float(avg_raw) if avg_raw is not None else 0.0
            sd_raw = item.get(sd_key)
            sd = float(sd_raw) if sd_raw is not None else 0.0
            sum_val = avg * count
            sum_sq = (sd ** 2 + avg ** 2) * count if count else 0.0
            stats[metric] = {"count": count, "sum": sum_val, "sum_sq": sum_sq}
            if count <= 0:
                item[cnt_key] = 0
                item[avg_key] = None
                item[sd_key] = None
            else:
                item[cnt_key] = count
                item[avg_key] = avg
                item[sd_key] = sd
        item.setdefault("tags", [])
        item.setdefault("knowledge_difficulty", None)
        item.setdefault("meta", {}).setdefault("tags", item.get("tags", []))
        if "knowledge_difficulty" in item and item["knowledge_difficulty"]:
                item["meta"].setdefault("knowledge_difficulty", item["knowledge_difficulty"])
        item["_stats"] = stats

    def _reset_problem_stats(self) -> None:
        for problem in self.problem_map.values():
            self._init_problem_stats(problem)
            problem["median_thinking"] = None
            problem["median_implementation"] = None
            problem["medium_difficulty"] = None
            problem["medium_quality"] = None

    def _rebuild_problem_stats(self) -> None:
        self._reset_problem_stats()
        for vote in self.store.get("votes", []):
            if vote.get("deleted"):
                continue
            problem_id = vote.get("problem_id")
            if not problem_id:
                continue
            self._adjust_problem_stats(
                problem_id,
                thinking=vote.get("thinking"),
                implementation=vote.get("implementation"),
                overall=vote.get("overall"),
                quality=vote.get("quality"),
            )

    def _update_problem_medians(self, problem_id: int) -> None:
        problem = self.problem_map.get(problem_id)
        if not problem:
            return
        votes = [
            vote for vote in self.store.get("votes", [])
            if vote.get("problem_id") == problem_id and not vote.get("deleted")
        ]
        if not votes:
            problem["median_thinking"] = None
            problem["median_implementation"] = None
            problem["medium_difficulty"] = None
            problem["medium_quality"] = None
            return
        thinking_values = [float(v["thinking"]) for v in votes if v.get("thinking") is not None]
        implementation_values = [float(v["implementation"]) for v in votes if v.get("implementation") is not None]
        overall_values = [float(v["overall"]) for v in votes if v.get("overall") is not None]
        quality_values = [float(v["quality"]) for v in votes if v.get("quality") is not None]
        problem["median_thinking"] = _median(thinking_values)
        problem["median_implementation"] = _median(implementation_values)
        problem["medium_difficulty"] = _median(overall_values)
        problem["medium_quality"] = _median(quality_values)

    def _save_store(self) -> None:
        STORE_PATH.write_text(json.dumps(self.store, ensure_ascii=False, indent=2), encoding="utf-8")
        self._store_mtime = self._store_file_mtime()

    def _store_file_mtime(self) -> float:
        try:
            return STORE_PATH.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    def _ensure_store_fresh(self) -> None:
        current_mtime = self._store_file_mtime()
        if current_mtime and current_mtime > getattr(self, "_store_mtime", 0.0):
            # Re-load store data when another process updates the backing file.
            self._load_store()

    def _normalise_course_id(self, value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            course_id = int(value)
        except (TypeError, ValueError):
            return None
        return course_id if course_id in self.types else None

    def _parse_time_string(self, value: Optional[str]) -> int:
        if not value:
            return _now_ts()
        try:
            return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").timestamp())
        except ValueError:
            return _now_ts()

    # Utility accessors -------------------------------------------------

    def list_types(self) -> List[Dict[str, Any]]:
        self._ensure_store_fresh()
        return sorted(self.types.values(), key=lambda item: item["id"])

    def list_type_groups(self) -> List[Dict[str, Any]]:
        self._ensure_store_fresh()
        groups = [{"label": group["label"], "entries": list(group["entries"])} for group in self.type_groups]
        if self.course_categories:
            for category_id in sorted(self.course_categories):
                category = self.course_categories[category_id]
                entries = []
                seen = set()
                for type_id, assigned_ids in self.type_categories.items():
                    if category_id in assigned_ids and type_id in self.types and type_id not in seen:
                        seen.add(type_id)
                        entries.append(self.types[type_id])
                if entries:
                    entries.sort(key=lambda item: item["name"])
                    groups.append({"label": category["name"], "entries": entries})
        if self.custom_types:
            custom_entries = [self.types[type_id] for type_id in sorted(self.custom_types)]
            groups.append({"label": "自定义课程", "entries": custom_entries})
        return groups

    def list_course_contests(self, type_id: int) -> List[Dict[str, Any]]:
        self._ensure_store_fresh()
        contests = self.store.get("course_contests", {}).get(str(type_id), [])
        return list(contests)

    def get_first_course_id(self) -> Optional[int]:
        self._ensure_store_fresh()
        return min(self.types.keys()) if self.types else None

    def get_global_default_course_id(self) -> Optional[int]:
        self._ensure_store_fresh()
        default_id = self._normalise_course_id(self.store.get("global_default_course_id"))
        return default_id

    def set_global_default_course(self, course_id: Optional[int]) -> None:
        self._ensure_store_fresh()
        if course_id is None:
            self.store["global_default_course_id"] = None
            self._save_store()
            return
        normalised = self._normalise_course_id(course_id)
        if normalised is None:
            raise ValueError("课程不存在")
        self.store["global_default_course_id"] = normalised
        self._save_store()

    def resolve_start_course_id(self, user: Optional[Dict[str, Any]] = None) -> Optional[int]:
        self._ensure_store_fresh()
        if user:
            preferred = self._normalise_course_id(user.get("default_course_id"))
            if preferred is not None:
                return preferred
        global_default = self.get_global_default_course_id()
        if global_default is not None:
            return global_default
        return self.get_first_course_id()

    def list_categories(self) -> List[Dict[str, Any]]:
        self._ensure_store_fresh()
        return sorted(self.course_categories.values(), key=lambda item: item["id"])

    def get_categories_for_course(self, type_id: int) -> List[Dict[str, Any]]:
        self._ensure_store_fresh()
        return [self.course_categories[cid] for cid in self.type_categories.get(type_id, []) if cid in self.course_categories]

    def get_category_ids_for_course(self, type_id: int) -> List[int]:
        self._ensure_store_fresh()
        return list(self.type_categories.get(type_id, []))

    def _normalise_category_ids(self, category_ids: Optional[Iterable[Any]]) -> List[int]:
        if not category_ids:
            return []
        normalised: List[int] = []
        seen = set()
        for raw_id in category_ids:
            try:
                category_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if category_id not in self.course_categories or category_id in seen:
                continue
            seen.add(category_id)
            normalised.append(category_id)
        return normalised

    def _set_course_categories(self, type_id: int, category_ids: Optional[Iterable[Any]], *, save: bool) -> None:
        if type_id not in self.types:
            raise ValueError("课程不存在")
        normalised = self._normalise_category_ids(category_ids)
        mapping = self.store.setdefault("type_categories", {})
        key = str(type_id)
        changed = False
        if normalised:
            changed = mapping.get(key) != normalised
            mapping[key] = normalised
            self.type_categories[type_id] = normalised
        else:
            if key in mapping:
                mapping.pop(key, None)
                changed = True
            if type_id in self.type_categories:
                self.type_categories.pop(type_id, None)
                changed = True
        if changed and save:
            self._save_store()

    def set_course_categories(self, type_id: int, category_ids: Iterable[Any]) -> None:
        self._set_course_categories(type_id, category_ids, save=True)

    def create_category(self, name: str) -> Dict[str, Any]:
        title = name.strip()
        if not title:
            raise ValueError("分类名称不能为空")
        if any(entry["name"] == title for entry in self.course_categories.values()):
            raise ValueError("分类已存在")
        category_id = self.store["next_category_id"]
        self.store["next_category_id"] += 1
        entry = {"id": category_id, "name": title}
        categories = self.store.setdefault("course_categories", [])
        categories.append(entry)
        categories.sort(key=lambda item: item["id"])
        self.course_categories[category_id] = entry
        self._save_store()
        return entry

    def delete_category(self, category_id: int) -> bool:
        if category_id not in self.course_categories:
            return False
        self.store["course_categories"] = [
            item for item in self.store.get("course_categories", []) if int(item.get("id", 0) or 0) != category_id
        ]
        self.course_categories.pop(category_id, None)
        mapping = self.store.setdefault("type_categories", {})
        for key in list(mapping.keys()):
            try:
                type_id = int(key)
            except (TypeError, ValueError):
                mapping.pop(key, None)
                continue
            filtered: List[int] = []
            for raw_category_id in mapping.get(key, []):
                try:
                    cid = int(raw_category_id)
                except (TypeError, ValueError):
                    continue
                if cid == category_id:
                    continue
                filtered.append(cid)
            if filtered:
                mapping[key] = filtered
                self.type_categories[type_id] = filtered
            else:
                mapping.pop(key, None)
                self.type_categories.pop(type_id, None)
        for type_id, ids in list(self.type_categories.items()):
            if category_id in ids:
                filtered_ids = [cid for cid in ids if cid != category_id]
                if filtered_ids:
                    self.type_categories[type_id] = filtered_ids
                else:
                    self.type_categories.pop(type_id, None)
        self._save_store()
        return True

    def create_course(self, name: str, category_ids: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
        title = name.strip()
        if not title:
            raise ValueError("课程名称不能为空")
        for item in self.types.values():
            if item["name"] == title:
                raise ValueError("课程已存在")
        type_id = self.store["next_type_id"]
        self.store["next_type_id"] += 1
        entry = {"id": type_id, "name": title}
        self.custom_types[type_id] = entry
        self.types[type_id] = entry
        self.store.setdefault("custom_types", []).append(entry)
        self.problems_by_type[type_id] = {"type": entry, "problems": []}
        self.store.setdefault("course_contests", {}).setdefault(str(type_id), [])
        self._set_course_categories(type_id, category_ids, save=False)
        self._save_store()
        return entry

    def delete_course(self, type_id: int) -> bool:
        if type_id not in self.custom_types:
            return False
        bucket = self.problems_by_type.get(type_id, {})
        cleanup_happened = False
        for problem in list(bucket.get("problems", [])):
            if self._delete_problem(problem["id"], require_custom=False, save=False):
                cleanup_happened = True
        if str(type_id) in self.store.get("course_contests", {}):
            contests = self.store.get("course_contests", {})
            if contests.pop(str(type_id), None) is not None:
                cleanup_happened = True
        self.store["custom_types"] = [item for item in self.store.get("custom_types", []) if item["id"] != type_id]
        self._set_course_categories(type_id, [], save=False)
        self.types.pop(type_id, None)
        self.custom_types.pop(type_id, None)
        self.problems_by_type.pop(type_id, None)
        cleanup_happened = True
        if cleanup_happened:
            if self.store.get("global_default_course_id") == type_id:
                self.store["global_default_course_id"] = None
            for user in self.store.get("users", []):
                if user.get("default_course_id") == type_id:
                    user["default_course_id"] = None
            self._save_store()
        return True

    def create_contest(self, type_id: int, name: str) -> Dict[str, Any]:
        if type_id not in self.types:
            raise ValueError("课程不存在")
        title = name.strip()
        if not title:
            raise ValueError("比赛名称不能为空")
        contests_map = self.store.setdefault("course_contests", {})
        bucket = contests_map.setdefault(str(type_id), [])
        if any(contest["name"] == title for contest in bucket):
            raise ValueError("比赛已存在")
        contest_id = self.store["next_contest_id"]
        self.store["next_contest_id"] += 1
        entry = {"id": contest_id, "name": title}
        bucket.append(entry)
        self._save_store()
        return entry

    def delete_contest(self, type_id: int, contest_id: int) -> bool:
        contests_map = self.store.setdefault("course_contests", {})
        bucket = contests_map.get(str(type_id))
        if not bucket:
            return False
        target = None
        remaining: List[Dict[str, Any]] = []
        for contest in bucket:
            if contest.get("id") == contest_id:
                target = contest
            else:
                remaining.append(contest)
        if not target:
            return False
        contests_map[str(type_id)] = remaining
        contest_name = target.get("name", "")
        if contest_name:
            custom_ids = {problem["id"] for problem in self.store.get("custom_problems", [])}
            for problem in list(self.problems_by_type.get(type_id, {}).get("problems", [])):
                if problem["id"] in custom_ids and problem.get("contest") == contest_name:
                    self._delete_problem(problem["id"], require_custom=False, save=False)
        self._save_store()
        return True

    def get_type_payload(self, type_id: int) -> Optional[Dict[str, Any]]:
        return self.problems_by_type.get(type_id)

    def get_problem(self, problem_id: int) -> Optional[Dict[str, Any]]:
        return self.problem_map.get(problem_id)

    # Announcement operations ------------------------------------------

    def newest_announcement_ts(self) -> int:
        if not self.store["announcements"]:
            return 0
        return max(item["created_at"] for item in self.store["announcements"])

    def list_announcements(self) -> List[Dict[str, Any]]:
        items = sorted(self.store["announcements"], key=lambda x: (-int(x.get("pinned", 0)), -x["created_at"]))
        return items

    def create_announcement(self, title: str, content: str, pinned: bool) -> None:
        announcement = {
            "id": self.store["next_announcement_id"],
            "title": title,
            "content": content,
            "pinned": pinned,
            "created_at": _now_ts(),
        }
        self.store["next_announcement_id"] += 1
        self.store["announcements"].append(announcement)
        self._save_store()

    def delete_announcement(self, announcement_id: int) -> bool:
        before = len(self.store["announcements"])
        self.store["announcements"] = [a for a in self.store["announcements"] if a["id"] != announcement_id]
        if len(self.store["announcements"]) != before:
            self._save_store()
            return True
        return False

    # User operations ---------------------------------------------------

    def find_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        username_lower = username.lower()
        for user in self.store.get("users", []):
            if user["username"].lower() == username_lower:
                return user
        return None

    def find_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        for user in self.store.get("users", []):
            if user["id"] == user_id:
                return user
        return None

    def register_user(self, username: str, password: str, luoguid: str, info: str) -> Dict[str, Any]:
        if self.find_user_by_username(username):
            raise ValueError("用户名已存在")
        user = {
            "id": self.store["next_user_id"],
            "username": username,
            "password_hash": generate_password_hash(password),
            "legacy_password_hash": None,
            "is_admin": False,
            "luoguid": luoguid,
            "info": info,
            "created_at": _now_ts(),
            "approved": False,
            "banned": False,
            "roles": [],
            "tag_permissions": [],
            "default_course_id": None,
        }
        self.store["next_user_id"] += 1
        self.store.setdefault("users", []).append(user)
        self._save_store()
        return user

    def update_password(self, user: Dict[str, Any], password: str) -> None:
        user["password_hash"] = generate_password_hash(password)
        user["legacy_password_hash"] = None
        self._save_store()

    def verify_user_password(self, user: Dict[str, Any], password: str) -> bool:
        if not user:
            return False
        password_hash = user.get("password_hash")
        if password_hash:
            try:
                if check_password_hash(password_hash, password):
                    return True
            except ValueError:
                pass
        legacy_hash = user.get("legacy_password_hash")
        if legacy_hash and _sha256_hex(password) == legacy_hash:
            self.update_password(user, password)
            return True
        return False

    def approve_user(self, user_id: int) -> bool:
        user = self.find_user_by_id(user_id)
        if not user:
            return False
        user["approved"] = True
        self._save_store()
        return True

    def reject_user(self, user_id: int) -> bool:
        users = self.store.get("users", [])
        before = len(users)
        self.store["users"] = [user for user in users if user["id"] != user_id]
        if len(self.store["users"]) != before:
            self._save_store()
            return True
        return False

    def set_admin(self, user_id: int, is_admin: bool) -> bool:
        user = self.find_user_by_id(user_id)
        if not user:
            return False
        user["is_admin"] = is_admin
        roles = set(user.get("roles", []))
        if is_admin:
            roles.add("admin")
        else:
            roles.discard("admin")
        user["roles"] = sorted(roles)
        self._save_store()
        return True

    def set_banned(self, user_id: int, banned: bool) -> bool:
        user = self.find_user_by_id(user_id)
        if not user:
            return False
        user["banned"] = banned
        self._save_store()
        return True

    def add_tag_permission(self, user_id: int, permission: str, *, save: bool = True) -> bool:
        user = self.find_user_by_id(user_id)
        if not user:
            return False
        perm = permission.strip()
        if not perm:
            raise ValueError("标签权限不能为空")
        perms = user.setdefault("tag_permissions", [])
        if perm in perms:
            return False
        perms.append(perm)
        if save:
            self._save_store()
        return True

    def remove_tag_permission(self, user_id: int, permission: str, *, save: bool = True) -> bool:
        user = self.find_user_by_id(user_id)
        if not user:
            return False
        perm = permission.strip()
        perms = user.setdefault("tag_permissions", [])
        if perm not in perms:
            return False
        user["tag_permissions"] = [p for p in perms if p != perm]
        if save:
            self._save_store()
        return True

    def set_user_default_course(self, user_id: int, course_id: Optional[int]) -> bool:
        user = self.find_user_by_id(user_id)
        if not user:
            return False
        if course_id is None or course_id == "":
            user["default_course_id"] = None
            self._save_store()
            return True
        normalised = self._normalise_course_id(course_id)
        if normalised is None:
            raise ValueError("课程不存在")
        user["default_course_id"] = normalised
        self._save_store()
        return True

    def clear_votes_for_user(self, user_id: int) -> int:
        cleared, _ = self._remove_votes_matching(lambda vote: vote.get("user_id") == user_id)
        return cleared

    # Vote operations ---------------------------------------------------

    def upsert_vote(
        self,
        user_id: int,
        problem_id: int,
        thinking: float,
        implementation: float,
        quality: Optional[float],
        comment: str,
        make_public: bool,
        *,
        save: bool = True,
    ) -> Dict[str, Any]:
        existing = None
        for vote in self.store.get("votes", []):
            if vote["user_id"] == user_id and vote["problem_id"] == problem_id:
                existing = vote
                break
        timestamp = _now_ts()
        thinking_val = float(thinking)
        implementation_val = float(implementation)
        overall_val = _calc_overall(thinking_val, implementation_val)
        quality_val = None if quality is None else float(quality)
        if existing:
            self._adjust_problem_stats(
                problem_id,
                thinking=existing.get("thinking"),
                implementation=existing.get("implementation"),
                overall=existing.get("overall") or existing.get("difficulty"),
                quality=existing.get("quality"),
                remove=True,
            )
            existing.update({
                "thinking": thinking_val,
                "implementation": implementation_val,
                "overall": overall_val,
                "difficulty": overall_val,
                "quality": quality_val,
                "comment": comment,
                "public": make_public,
                "deleted": False,
                "accepted": True,
                "score": existing.get("score", 0),
                "updated_at": timestamp,
            })
            self._adjust_problem_stats(
                problem_id,
                thinking=thinking_val,
                implementation=implementation_val,
                overall=overall_val,
                quality=quality_val,
            )
            if save:
                self._save_store()
            return existing
        vote = {
            "id": self.store["next_vote_id"],
            "user_id": user_id,
            "problem_id": problem_id,
            "thinking": thinking_val,
            "implementation": implementation_val,
            "overall": overall_val,
            "difficulty": overall_val,
            "quality": quality_val,
            "comment": comment,
            "public": make_public,
            "deleted": False,
            "accepted": True,
            "score": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.store["next_vote_id"] += 1
        self.store.setdefault("votes", []).append(vote)
        self._adjust_problem_stats(
            problem_id,
            thinking=thinking_val,
            implementation=implementation_val,
            overall=overall_val,
            quality=quality_val,
        )
        if save:
            self._save_store()
        return vote

    def _adjust_problem_stats(
        self,
        problem_id: int,
        *,
        thinking: Optional[float],
        implementation: Optional[float],
        overall: Optional[float],
        quality: Optional[float],
        remove: bool = False,
    ) -> None:
        problem = self.problem_map.get(problem_id)
        if not problem:
            return
        stats = problem.get("_stats", {})
        if not stats:
            return

        def update_metric(metric: str, value: Optional[float]) -> None:
            if value is None or metric not in stats:
                return
            block = stats[metric]
            if remove:
                block["count"] = max(0, block["count"] - 1)
                block["sum"] -= value
                block["sum_sq"] -= value ** 2
                if block["count"] <= 0:
                    block["sum"] = 0.0
                    block["sum_sq"] = 0.0
            else:
                block["count"] += 1
                block["sum"] += value
                block["sum_sq"] += value ** 2
            block["sum_sq"] = max(0.0, block["sum_sq"])
            mapping = PROBLEM_STATS_SPECS[metric]
            count = block["count"]
            if count <= 0:
                problem[mapping["cnt"]] = 0
                problem[mapping["avg"]] = None
                problem[mapping["sd"]] = None
                block["sum"] = 0.0
                block["sum_sq"] = 0.0
                return
            avg = block["sum"] / count
            variance = max(0.0, block["sum_sq"] / count - avg ** 2)
            problem[mapping["cnt"]] = count
            problem[mapping["avg"]] = avg
            problem[mapping["sd"]] = variance ** 0.5

        update_metric("thinking", thinking)
        update_metric("implementation", implementation)
        update_metric("overall", overall)
        update_metric("quality", quality)
        self._update_problem_medians(problem_id)

    def _remove_votes_matching(self, predicate: Callable[[Dict[str, Any]], bool]) -> Tuple[int, List[int]]:
        votes = self.store.get("votes", [])
        if not votes:
            return 0, []
        remaining_votes: List[Dict[str, Any]] = []
        removed_vote_ids: List[int] = []
        cleared = 0
        for vote in votes:
            if not predicate(vote):
                remaining_votes.append(vote)
                continue
            try:
                vote_id = int(vote.get("id", 0) or 0)
            except (TypeError, ValueError):
                vote_id = 0
            removed_vote_ids.append(vote_id)
            if not vote.get("deleted"):
                self._adjust_problem_stats(
                    vote.get("problem_id"),
                    thinking=vote.get("thinking"),
                    implementation=vote.get("implementation"),
                    overall=vote.get("overall") or vote.get("difficulty"),
                    quality=vote.get("quality"),
                    remove=True,
                )
                cleared += 1
        if not removed_vote_ids:
            return cleared, removed_vote_ids
        self.store["votes"] = remaining_votes
        reports = self.store.get("reports", [])
        if reports:
            self.store["reports"] = [item for item in reports if item.get("vote_id") not in removed_vote_ids]
        self._save_store()
        return cleared, removed_vote_ids

    def list_votes_for_problem(self, problem_id: int) -> List[Dict[str, Any]]:
        votes = []
        for vote in self.store.get("votes", []):
            if vote["problem_id"] == problem_id:
                votes.append(dict(vote))
        return votes

    def find_vote_by_id(self, vote_id: int) -> Optional[Dict[str, Any]]:
        self._ensure_store_fresh()
        try:
            target_id = int(vote_id)
        except (TypeError, ValueError):
            return None
        if target_id <= 0:
            return None
        for vote in self.store.get("votes", []):
            if vote.get("id") == target_id:
                return dict(vote)
        return None

    def mark_vote_deleted(self, vote_id: int) -> bool:
        cleared, removed_ids = self._remove_votes_matching(lambda vote: vote.get("id") == vote_id)
        return bool(removed_ids or cleared)

    def mark_votes_deleted_bulk(self, vote_ids: List[int]) -> int:
        try:
            target_ids = {int(vote_id) for vote_id in vote_ids}
        except (TypeError, ValueError):
            target_ids = set()
        if not target_ids:
            return 0
        cleared, _ = self._remove_votes_matching(lambda vote: vote.get("id") in target_ids)
        return cleared

    def report_vote(self, vote_id: int, user_id: int) -> Tuple[bool, Optional[str]]:
        self._ensure_store_fresh()
        try:
            vote_id_int = int(vote_id)
            reporter_id = int(user_id)
        except (TypeError, ValueError):
            return False, "Invalid vote"
        if vote_id_int <= 0 or reporter_id <= 0:
            return False, "Invalid vote"
        vote = None
        for entry in self.store.get("votes", []):
            if entry.get("id") == vote_id_int:
                vote = entry
                break
        if not vote or vote.get("deleted"):
            return False, "Vote not found"
        for report in self.store.get("reports", []):
            if report.get("vote_id") == vote_id_int and report.get("user_id") == reporter_id:
                return False, "Already reported"
        report_id = max(1, int(self.store.get("next_report_id", 1) or 1))
        self.store["next_report_id"] = report_id + 1
        target_user_id = None
        try:
            target_user_id = int(vote.get("user_id") or 0) or None
        except (TypeError, ValueError):
            target_user_id = None
        self.store.setdefault("reports", []).append({
            "id": report_id,
            "vote_id": vote_id_int,
            "user_id": reporter_id,
            "reporter_id": reporter_id,
            "target_user_id": target_user_id,
            "created_at": _now_ts(),
        })
        self._save_store()
        return True, None

    def list_reports(self) -> List[Dict[str, Any]]:
        self._ensure_store_fresh()
        return [dict(report) for report in self.store.get("reports", [])]

    def get_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        self._ensure_store_fresh()
        try:
            rid = int(report_id)
        except (TypeError, ValueError):
            return None
        if rid <= 0:
            return None
        for report in self.store.get("reports", []):
            if report.get("id") == rid:
                return dict(report)
        return None

    def remove_report(self, report_id: int) -> bool:
        self._ensure_store_fresh()
        try:
            rid = int(report_id)
        except (TypeError, ValueError):
            return False
        if rid <= 0:
            return False
        reports = self.store.get("reports", [])
        before = len(reports)
        self.store["reports"] = [report for report in reports if report.get("id") != rid]
        if len(self.store["reports"]) != before:
            self._save_store()
            return True
        return False

    # Problem mutations -------------------------------------------------

    def apply_problem_edit(self, pid: int, payload: Dict[str, Any]) -> bool:
        problem = self.problem_map.get(pid)
        if not problem:
            return False
        problem.update(payload)
        self.store.setdefault("problem_overrides", {})[str(pid)] = payload
        self._save_store()
        return True

    def create_problem(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        problem_id = self.store["next_problem_id"]
        self.store["next_problem_id"] += 1
        payload = dict(payload)
        payload.setdefault("meta", {})
        payload.setdefault("setter", [])
        payload.setdefault("source", [])
        payload.setdefault("url", "")
        payload.setdefault("description", "")
        payload.setdefault("contest", "")
        payload.setdefault("tags", [])
        payload.setdefault("knowledge_difficulty", None)
        payload.setdefault("avg_difficulty", None)
        payload.setdefault("avg_quality", None)
        payload.setdefault("sd_difficulty", None)
        payload.setdefault("sd_quality", None)
        payload.setdefault("cnt1", 0)
        payload.setdefault("cnt2", 0)
        payload.setdefault("medium_difficulty", None)
        payload.setdefault("medium_quality", None)
        payload["id"] = problem_id
        payload["is_custom"] = True
        meta = payload.setdefault("meta", {})
        meta.setdefault("tags", list(payload.get("tags", [])))
        if payload.get("knowledge_difficulty"):
            meta.setdefault("knowledge_difficulty", payload["knowledge_difficulty"])
        self._init_problem_stats(payload)
        self.store.setdefault("custom_problems", []).append(payload)
        self.problem_map[problem_id] = payload
        bucket = self.problems_by_type.setdefault(payload["type"], {"type": self.types.get(payload["type"], {"id": payload["type"], "name": ""}), "problems": []})
        bucket["problems"].append(payload)
        self._save_store()
        return payload

    def delete_problem(self, problem_id: int) -> bool:
        custom_ids = {problem["id"] for problem in self.store.get("custom_problems", [])}
        if problem_id not in custom_ids:
            raise ValueError("只能删除自定义题目")
        if not self._delete_problem(problem_id, require_custom=False, save=True):
            raise ValueError("题目不存在或无法删除")
        return True

    def update_problem_meta(
        self,
        problem_id: int,
        tags: Iterable[str],
        knowledge_difficulty: Optional[str],
        *,
        save: bool = True,
    ) -> bool:
        problem = self.problem_map.get(problem_id)
        if not problem:
            return False
        cleaned_tags: List[str] = []
        seen = set()
        for tag in tags or []:
            tag_str = str(tag).strip()
            if tag_str and tag_str not in seen:
                seen.add(tag_str)
                cleaned_tags.append(tag_str)
        knowledge_value = knowledge_difficulty.strip() if knowledge_difficulty else None
        problem["tags"] = cleaned_tags
        problem["knowledge_difficulty"] = knowledge_value
        meta = problem.setdefault("meta", {})
        meta["tags"] = cleaned_tags
        if knowledge_value:
            meta["knowledge_difficulty"] = knowledge_value
        else:
            meta.pop("knowledge_difficulty", None)
        overrides = self.store.setdefault("problem_overrides", {})
        entry = dict(overrides.get(str(problem_id), {}))
        entry["tags"] = cleaned_tags
        entry["knowledge_difficulty"] = knowledge_value
        meta_override = dict(entry.get("meta", {}))
        meta_override["tags"] = cleaned_tags
        if knowledge_value:
            meta_override["knowledge_difficulty"] = knowledge_value
        else:
            meta_override.pop("knowledge_difficulty", None)
        entry["meta"] = meta_override
        overrides[str(problem_id)] = entry
        if save:
            self._save_store()
        return True

    def can_user_edit_problem_meta(self, user: Optional[Dict[str, Any]], problem_id: int) -> bool:
        if not user:
            return False
        if user.get("is_admin"):
            return True
        problem = self.problem_map.get(problem_id)
        if not problem:
            return False
        title = problem.get("title", "")
        for perm in user.get("tag_permissions", []) or []:
            if perm and perm in title:
                return True
        return False

    def import_legacy_config(
        self,
        *,
        users_path: Path,
        votes_path: Path,
        problems_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        summary = {
            "users_created": 0,
            "users_updated": 0,
            "tag_permissions_updated": 0,
            "problems_created": 0,
            "problems_updated": 0,
            "votes_imported": 0,
            "votes_updated": 0,
            "skipped_votes": 0,
        }

        if not users_path.exists() or not votes_path.exists():
            raise FileNotFoundError("缺少 legacy 配置文件")

        legacy_users = json.loads(users_path.read_text(encoding="utf-8"))
        legacy_votes_payload = json.loads(votes_path.read_text(encoding="utf-8"))
        legacy_votes = legacy_votes_payload.get("votes", {})
        legacy_comments = legacy_votes_payload.get("comments", {})
        legacy_problem_metas = legacy_votes_payload.get("problem_metas", {})

        legacy_urls: Dict[str, str] = {}
        if problems_path and problems_path.exists():
            lines = [line.strip() for line in problems_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            for idx in range(0, len(lines), 2):
                title = lines[idx]
                url = lines[idx + 1] if idx + 1 < len(lines) else ""
                legacy_urls[title] = url

        def ensure_category_id(name: str) -> int:
            for category in self.store.get("course_categories", []):
                if category.get("name") == name:
                    return int(category.get("id"))
            entry = self.create_category(name)
            return entry["id"]

        def ensure_course_id(name: str, category_id: int) -> int:
            for type_id, info in self.types.items():
                if info.get("name") == name:
                    self.set_course_categories(type_id, [category_id])
                    return type_id
            entry = self.create_course(name, [category_id])
            return entry["id"]

        legacy_category_id = ensure_category_id("legacy")
        legacy_course_id = ensure_course_id("25年暑期题单", legacy_category_id)

        user_lookup = {user["username"].lower(): user for user in self.store.get("users", [])}
        for username, info in legacy_users.items():
            username_lower = username.lower()
            created = False
            if username_lower in user_lookup:
                user = user_lookup[username_lower]
                summary["users_updated"] += 1
            else:
                user = {
                    "id": self.store["next_user_id"],
                    "username": username,
                    "password_hash": None,
                    "legacy_password_hash": None,
                    "is_admin": False,
                    "luoguid": "",
                    "info": "",
                    "created_at": int(info.get("created_at", _now_ts())),
                    "approved": True,
                    "banned": False,
                    "roles": [],
                    "tag_permissions": [],
                }
                self.store["next_user_id"] += 1
                self.store.setdefault("users", []).append(user)
                user_lookup[username_lower] = user
                summary["users_created"] += 1
                created = True
            user["legacy_password_hash"] = info.get("password")
            if created or not user.get("password_hash"):
                user["password_hash"] = user.get("password_hash")
            user["is_admin"] = bool(info.get("is_admin"))
            user["banned"] = bool(info.get("banned", False))
            roles = set(user.get("roles", []))
            if user["is_admin"]:
                roles.add("admin")
            else:
                roles.discard("admin")
            user["roles"] = sorted(roles)
            perms_before = set(user.get("tag_permissions", []))
            perms_after = set(perms_before)
            for perm in info.get("tag_permissions", []) or []:
                perm_str = str(perm).strip()
                if perm_str:
                    perms_after.add(perm_str)
            if perms_after != perms_before:
                user["tag_permissions"] = sorted(perms_after)
                summary["tag_permissions_updated"] += 1

        comment_lookup: Dict[Tuple[str, str], str] = {}
        for problem_title, entries in legacy_comments.items():
            for entry in entries or []:
                author = str(entry.get("user", "")).strip()
                text = str(entry.get("text", "")).strip()
                if not author or not text:
                    continue
                key = (problem_title, author)
                if key in comment_lookup:
                    comment_lookup[key] = comment_lookup[key] + "\n" + text
                else:
                    comment_lookup[key] = text

        def derive_contest_name(title: str) -> str:
            token = title[:6]
            if token.isdigit():
                year = int(token[:2])
                month = int(token[2:4])
                day = int(token[4:6])
                year += 2000
                try:
                    return f"{year:04d}-{month:02d}-{day:02d}"
                except ValueError:
                    return token
            return token if token else "Legacy"

        for problem_title, votes in legacy_votes.items():
            contest_name = derive_contest_name(problem_title)
            existing_problem = None
            bucket = self.problems_by_type.get(legacy_course_id, {}).get("problems", [])
            for problem in bucket:
                if problem.get("title") == problem_title:
                    existing_problem = problem
                    break
            if existing_problem:
                summary["problems_updated"] += 1
            else:
                payload = {
                    "type": legacy_course_id,
                    "contest": contest_name,
                    "title": problem_title,
                    "url": legacy_urls.get(problem_title, ""),
                    "description": "",
                }
                existing_problem = self.create_problem(payload)
                summary["problems_created"] += 1
                bucket = self.problems_by_type.get(legacy_course_id, {}).get("problems", [])

            if existing_problem.get("contest") != contest_name:
                existing_problem["contest"] = contest_name
            if not existing_problem.get("url") and legacy_urls.get(problem_title):
                existing_problem["url"] = legacy_urls[problem_title]

            meta_info = legacy_problem_metas.get(problem_title, {}) or {}
            tags_text = meta_info.get("tags", "")
            tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]
            knowledge_level = meta_info.get("difficulty")
            self.update_problem_meta(existing_problem["id"], tags, knowledge_level, save=False)

            for vote in votes or []:
                voter = str(vote.get("voter", "")).strip()
                if not voter:
                    summary["skipped_votes"] += 1
                    continue
                voter_user = user_lookup.get(voter.lower())
                if not voter_user:
                    summary["skipped_votes"] += 1
                    continue
                thinking_val = float(vote.get("thinking", vote.get("difficulty", 0)))
                implementation_val = float(vote.get("implementing", vote.get("implementation", vote.get("difficulty", 0))))
                quality_val = vote.get("quality")
                comment = comment_lookup.get((problem_title, voter), "")
                previous_vote = None
                for existing_vote in self.store.get("votes", []):
                    if existing_vote["user_id"] == voter_user["id"] and existing_vote["problem_id"] == existing_problem["id"]:
                        previous_vote = existing_vote
                        break
                result = self.upsert_vote(
                    voter_user["id"],
                    existing_problem["id"],
                    thinking_val,
                    implementation_val,
                    quality_val,
                    comment,
                    False,
                    save=False,
                )
                if previous_vote and previous_vote is result:
                    summary["votes_updated"] += 1
                elif previous_vote:
                    summary["votes_updated"] += 1
                else:
                    summary["votes_imported"] += 1

        self._rebuild_problem_stats()
        self._save_store()
        return summary

    def _delete_problem(self, problem_id: int, require_custom: bool, save: bool) -> bool:
        problem = self.problem_map.get(problem_id)
        if not problem:
            return False
        if require_custom:
            custom_ids = {entry["id"] for entry in self.store.get("custom_problems", [])}
            if problem_id not in custom_ids:
                return False
        changed = False
        custom_problems = self.store.get("custom_problems", [])
        filtered_custom = [item for item in custom_problems if item.get("id") != problem_id]
        if len(filtered_custom) != len(custom_problems):
            self.store["custom_problems"] = filtered_custom
            changed = True
        overrides = self.store.get("problem_overrides", {})
        if overrides.pop(str(problem_id), None) is not None:
            changed = True
        removed_vote_ids = []
        votes = self.store.get("votes", [])
        remaining_votes = []
        for vote in votes:
            if vote.get("problem_id") == problem_id:
                removed_vote_ids.append(vote.get("id"))
            else:
                remaining_votes.append(vote)
        if len(remaining_votes) != len(votes):
            self.store["votes"] = remaining_votes
            changed = True
        if removed_vote_ids:
            reports = self.store.get("reports", [])
            remaining_reports = [item for item in reports if item.get("vote_id") not in removed_vote_ids]
            if len(remaining_reports) != len(reports):
                self.store["reports"] = remaining_reports
                changed = True
        type_id = problem.get("type")
        bucket = self.problems_by_type.get(type_id)
        if bucket:
            bucket["problems"] = [entry for entry in bucket.get("problems", []) if entry.get("id") != problem_id]
        self.problem_map.pop(problem_id, None)
        changed = True
        if changed and save:
            self._save_store()
        return True
