"""Data access layer for USACO Rating app."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROBLEMS_PATH = DATA_DIR / "problems.json"
TYPES_PATH = DATA_DIR / "types.json"
STORE_PATH = DATA_DIR / "store.json"
ANNOUNCEMENTS_SEED_PATH = DATA_DIR / "announcements.json"


def _now_ts() -> int:
    return int(time.time())


class DataStore:
    def __init__(self) -> None:
        self._load_types()
        self._load_problems()
        self.custom_types: Dict[int, Dict[str, Any]] = {}
        self._load_store()
        self._bootstrap_announcements()

    def _load_types(self) -> None:
        payload = json.loads(TYPES_PATH.read_text(encoding="utf-8"))
        self.types = {item["id"]: item for item in payload["types"]}
        self.type_groups = []
        for group in payload.get("groups", []):
            entries = [self.types[tid] for tid in group.get("type_ids", []) if tid in self.types]
            if entries:
                self.type_groups.append({"label": group.get("label", ""), "entries": entries})

    def _load_problems(self) -> None:
        payload: Dict[str, Any] = json.loads(PROBLEMS_PATH.read_text(encoding="utf-8"))
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
        self.store = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        self.store.setdefault("announcements", [])
        self.store.setdefault("reports", [])
        self.store.setdefault("problem_overrides", {})
        self.store.setdefault("custom_problems", [])
        self.store.setdefault("custom_types", [])
        self.store.setdefault("course_contests", {})
        self.store.setdefault("next_problem_id", self.next_problem_id)
        self.store.setdefault("next_user_id", 1)
        self.store.setdefault("next_vote_id", 1)
        self.store.setdefault("next_contest_id", 1)
        users = self.store.setdefault("users", [])
        for user in users:
            user.setdefault("approved", user.get("is_admin", False))
            user.setdefault("banned", False)
            user.setdefault("roles", [])
            if user.get("is_admin") and "admin" not in user["roles"]:
                user["roles"].append("admin")
        if self.store["next_problem_id"] < self.next_problem_id:
            self.store["next_problem_id"] = self.next_problem_id

        existing_type_ids = list(self.types.keys())
        self.custom_types = {}
        normalised_custom_types = []
        for raw_type in self.store.get("custom_types", []):
            type_id = int(raw_type.get("id", 0) or 0)
            name = str(raw_type.get("name", "")).strip()
            if not type_id or not name:
                continue
            entry = {"id": type_id, "name": name}
            normalised_custom_types.append(entry)
            self.types[type_id] = entry
            self.custom_types[type_id] = entry
            self.problems_by_type.setdefault(type_id, {"type": entry, "problems": []})
            existing_type_ids.append(type_id)
        self.store["custom_types"] = normalised_custom_types
        proposed_next_type = max(existing_type_ids or [0]) + 1
        if self.store.get("next_type_id", 0) < proposed_next_type:
            self.store["next_type_id"] = proposed_next_type

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

    def _bootstrap_announcements(self) -> None:
        if self.store["announcements"]:
            existing_ids = [item.get("id", 0) for item in self.store["announcements"]]
            self.store.setdefault("next_announcement_id", max(existing_ids, default=0) + 1)
            return
        seed = json.loads(ANNOUNCEMENTS_SEED_PATH.read_text(encoding="utf-8"))
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

    def _init_problem_stats(self, item: Dict[str, Any]) -> None:
        stats = {}
        for key, cnt_key, avg_key, sd_key in (("difficulty", "cnt1", "avg_difficulty", "sd_difficulty"), ("quality", "cnt2", "avg_quality", "sd_quality")):
            count = int(item.get(cnt_key) or 0)
            avg = float(item.get(avg_key) or 0.0)
            sd = float(item.get(sd_key) or 0.0)
            sum_val = avg * count
            sum_sq = (sd ** 2 + avg ** 2) * count if count else 0.0
            stats[key] = {"count": count, "sum": sum_val, "sum_sq": sum_sq}
        item["_stats"] = stats

    def _save_store(self) -> None:
        STORE_PATH.write_text(json.dumps(self.store, ensure_ascii=False, indent=2), encoding="utf-8")

    def _parse_time_string(self, value: Optional[str]) -> int:
        if not value:
            return _now_ts()
        try:
            return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").timestamp())
        except ValueError:
            return _now_ts()

    # Utility accessors -------------------------------------------------

    def list_types(self) -> List[Dict[str, Any]]:
        return sorted(self.types.values(), key=lambda item: item["id"])

    def list_type_groups(self) -> List[Dict[str, Any]]:
        groups = [{"label": group["label"], "entries": list(group["entries"])} for group in self.type_groups]
        if self.custom_types:
            custom_entries = [self.types[type_id] for type_id in sorted(self.custom_types)]
            groups.append({"label": "自定义课程", "entries": custom_entries})
        return groups

    def list_course_contests(self, type_id: int) -> List[Dict[str, Any]]:
        contests = self.store.get("course_contests", {}).get(str(type_id), [])
        return list(contests)

    def create_course(self, name: str) -> Dict[str, Any]:
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
        self.types.pop(type_id, None)
        self.custom_types.pop(type_id, None)
        self.problems_by_type.pop(type_id, None)
        cleanup_happened = True
        if cleanup_happened:
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
            "is_admin": False,
            "luoguid": luoguid,
            "info": info,
            "created_at": _now_ts(),
            "approved": False,
            "banned": False,
            "roles": [],
        }
        self.store["next_user_id"] += 1
        self.store.setdefault("users", []).append(user)
        self._save_store()
        return user

    def update_password(self, user: Dict[str, Any], password: str) -> None:
        user["password_hash"] = generate_password_hash(password)
        self._save_store()

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

    def clear_votes_for_user(self, user_id: int) -> int:
        cleared = 0
        for vote in self.store.get("votes", []):
            if vote["user_id"] == user_id and not vote.get("deleted"):
                self._adjust_problem_stats(vote["problem_id"], vote["difficulty"], vote["quality"], remove=True)
                vote["deleted"] = True
                cleared += 1
        if cleared:
            self._save_store()
        return cleared

    # Vote operations ---------------------------------------------------

    def upsert_vote(self, user_id: int, problem_id: int, difficulty: int, quality: float, comment: str, make_public: bool) -> Dict[str, Any]:
        existing = None
        for vote in self.store.get("votes", []):
            if vote["user_id"] == user_id and vote["problem_id"] == problem_id:
                existing = vote
                break
        timestamp = _now_ts()
        if existing:
            self._adjust_problem_stats(problem_id, existing["difficulty"], existing["quality"], remove=True)
            existing.update({
                "difficulty": difficulty,
                "quality": quality,
                "comment": comment,
                "public": make_public,
                "deleted": False,
                "updated_at": timestamp,
            })
            self._adjust_problem_stats(problem_id, difficulty, quality)
            self._save_store()
            return existing
        vote = {
            "id": self.store["next_vote_id"],
            "user_id": user_id,
            "problem_id": problem_id,
            "difficulty": difficulty,
            "quality": quality,
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
        self._adjust_problem_stats(problem_id, difficulty, quality)
        self._save_store()
        return vote

    def _adjust_problem_stats(self, problem_id: int, difficulty: Optional[float], quality: Optional[float], remove: bool = False) -> None:
        problem = self.problem_map.get(problem_id)
        if not problem:
            return
        stats = problem.get("_stats", {})
        if not stats:
            return
        if difficulty is not None:
            block = stats["difficulty"]
            if remove:
                block["count"] = max(0, block["count"] - 1)
                block["sum"] -= difficulty
                block["sum_sq"] = max(0.0, block["sum_sq"] - difficulty ** 2)
            else:
                block["count"] += 1
                block["sum"] += difficulty
                block["sum_sq"] += difficulty ** 2
            self._recompute_problem_metric(problem, "difficulty")
        if quality is not None:
            block = stats["quality"]
            if remove:
                block["count"] = max(0, block["count"] - 1)
                block["sum"] -= quality
                block["sum_sq"] = max(0.0, block["sum_sq"] - quality ** 2)
            else:
                block["count"] += 1
                block["sum"] += quality
                block["sum_sq"] += quality ** 2
            self._recompute_problem_metric(problem, "quality")

    def _recompute_problem_metric(self, problem: Dict[str, Any], metric: str) -> None:
        block = problem["_stats"][metric]
        count = block["count"]
        if count <= 0:
            if metric == "difficulty":
                problem["avg_difficulty"] = None
                problem["sd_difficulty"] = None
                problem["cnt1"] = 0
            else:
                problem["avg_quality"] = None
                problem["sd_quality"] = None
                problem["cnt2"] = 0
            return
        avg = block["sum"] / count
        variance = max(0.0, block["sum_sq"] / count - avg ** 2)
        sd = variance ** 0.5
        if metric == "difficulty":
            problem["avg_difficulty"] = avg
            problem["sd_difficulty"] = sd
            problem["cnt1"] = count
        else:
            problem["avg_quality"] = avg
            problem["sd_quality"] = sd
            problem["cnt2"] = count

    def list_votes_for_problem(self, problem_id: int) -> List[Dict[str, Any]]:
        votes = []
        for vote in self.store.get("votes", []):
            if vote["problem_id"] == problem_id:
                votes.append(dict(vote))
        return votes

    def mark_vote_deleted(self, vote_id: int) -> bool:
        for vote in self.store.get("votes", []):
            if vote["id"] == vote_id:
                vote["deleted"] = True
                self._save_store()
                return True
        return False

    def mark_votes_deleted_bulk(self, vote_ids: List[int]) -> int:
        try:
            target_ids = {int(vote_id) for vote_id in vote_ids}
        except (TypeError, ValueError):
            target_ids = set()
        updated = 0
        if not target_ids:
            return 0
        for vote in self.store.get("votes", []):
            if vote["id"] in target_ids and not vote.get("deleted"):
                vote["deleted"] = True
                updated += 1
        if updated:
            self._save_store()
        return updated

    def report_vote(self, vote_id: int, user_id: int) -> None:
        self.store["reports"].append({
            "vote_id": vote_id,
            "user_id": user_id,
            "created_at": _now_ts(),
        })
        self._save_store()

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
