"""API route registration."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List

from flask import g, jsonify, request

from ..auth import api_user_guard
from ..datastore import DataStore


def register_api_routes(app) -> None:
    datastore: DataStore = app.config["DATASTORE"]

    @app.get("/api/announcement/newest")
    def api_newest_announcement() -> Any:
        return jsonify({"time": datastore.newest_announcement_ts()})

    @app.get("/api/announcements")
    def api_announcements() -> Any:
        result = []
        for item in datastore.list_announcements():
            result.append({
                "title": item["title"],
                "content": item["content"],
                "pinned": bool(item["pinned"]),
                "time": datetime.utcfromtimestamp(item["created_at"]).strftime("%Y-%m-%d %H:%M:%S"),
            })
        return jsonify({"announcements": result})

    @app.get("/api/problems")
    def api_problems() -> Any:
        try:
            type_id = int(request.args.get("type", 0) or 0)
        except ValueError:
            type_id = 0
        payload = datastore.get_type_payload(type_id)
        if not payload:
            fallback_id = datastore.resolve_start_course_id(getattr(g, "user", None))
            if fallback_id is not None:
                payload = datastore.get_type_payload(fallback_id)
                type_id = fallback_id
            if not payload:
                payload = {"type": {"id": type_id, "name": ""}, "problems": []}
        active_user = getattr(g, "user", None)
        for item in payload.get("problems", []):
            item.setdefault("tags", item.get("tags") or item.get("meta", {}).get("tags", []))
            knowledge = item.get("knowledge_difficulty") or item.get("meta", {}).get("knowledge_difficulty")
            if knowledge:
                item["knowledge_difficulty"] = knowledge
            if active_user:
                item["can_edit_meta"] = datastore.can_user_edit_problem_meta(active_user, item.get("id"))
            else:
                item["can_edit_meta"] = False
        return jsonify(payload)

    @app.get("/api/uservotes")
    def api_user_votes() -> Any:
        user, error = api_user_guard()
        if error:
            return jsonify(error)
        try:
            type_id = int(request.args.get("type", 0) or 0)
        except ValueError:
            type_id = 0
        voted = []
        for vote in datastore.store.get("votes", []):
            if vote["user_id"] == user["id"] and not vote.get("deleted"):
                problem = datastore.get_problem(vote["problem_id"])
                if not problem:
                    continue
                if type_id and problem.get("type") != type_id:
                    continue
                voted.append(problem["id"])
        return jsonify({"voted_problems": voted})

    @app.get("/api/queryvote")
    def api_query_vote() -> Any:
        user, error = api_user_guard()
        if error:
            return jsonify(error)
        try:
            problem_id = int(request.args.get("pid", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid problem"})
        problem = datastore.get_problem(problem_id)
        if not problem:
            return jsonify({"error": "Problem not found"})
        existing = None
        for vote in datastore.store.get("votes", []):
            if vote["user_id"] == user["id"] and vote["problem_id"] == problem_id and not vote.get("deleted"):
                existing = vote
                break
        default_thinking = existing.get("thinking") if existing else float(problem.get("avg_thinking") or problem.get("avg_difficulty") or 2000)
        default_implementation = existing.get("implementation") if existing else float(problem.get("avg_implementation") or problem.get("avg_difficulty") or 2000)
        default_quality = existing.get("quality") if existing else float(problem.get("avg_quality") or 3.0)
        overall_default = existing.get("overall") if existing else float(problem.get("avg_difficulty") or 2000)
        response = {
            "title": problem["title"],
            "url": problem.get("url", ""),
            "contest": problem.get("contest", ""),
            "description": problem.get("description", ""),
            "thinking": int(round(default_thinking)),
            "implementation": int(round(default_implementation)),
            "quality": round(default_quality, 2),
            "difficulty": int(round(overall_default)),
            "comment": existing.get("comment", "") if existing else "",
            "public": bool(existing.get("public")) if existing else False,
        }
        return jsonify(response)

    @app.post("/api/vote")
    def api_vote() -> Any:
        user, error = api_user_guard()
        if error:
            return jsonify(error)
        try:
            problem_id = int(request.form.get("pid", 0))
            thinking_raw = request.form.get("thinking")
            implementation_raw = request.form.get("implementation")
            if thinking_raw is None:
                thinking_raw = request.form.get("diff", "0")
            if implementation_raw is None:
                implementation_raw = request.form.get("impl", thinking_raw)
            thinking = float(thinking_raw)
            implementation = float(implementation_raw)
            quality_raw = request.form.get("quality")
            if quality_raw is None:
                quality_raw = request.form.get("qual")
            quality = float(quality_raw) if quality_raw not in {None, "", "null"} else None
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid input"})
        comment = request.form.get("comment", "")
        make_public = request.form.get("public") in {"true", "True", "1", "on", "yes"}
        if not (800 <= thinking <= 3500 and 800 <= implementation <= 3500):
            return jsonify({"error": "Out of range"})
        if quality is not None and not (-5 <= quality <= 5):
            return jsonify({"error": "Out of range"})
        problem = datastore.get_problem(problem_id)
        if not problem:
            return jsonify({"error": "Problem not found"})
        datastore.upsert_vote(user["id"], problem_id, thinking, implementation, quality, comment, make_public)
        return jsonify({"success": True})

    @app.get("/api/check")
    def api_check() -> Any:
        if not g.user or not g.user.get("is_admin"):
            return jsonify({"error": "Not authorized"})
        return jsonify({"username": g.user["username"], "admin": True})

    @app.post("/api/editp")
    def api_edit_problem() -> Any:
        if not g.user or not g.user.get("is_admin"):
            return jsonify({"error": "Not authorized"})
        try:
            pid = int(request.form.get("pid", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid problem"})
        payload = {
            "contest": request.form.get("contest", "").strip(),
            "title": request.form.get("title", "").strip(),
            "url": request.form.get("url", "").strip(),
            "description": request.form.get("des", "").strip(),
        }
        meta_raw = request.form.get("meta")
        if meta_raw:
            try:
                payload["meta"] = json.loads(meta_raw)
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid meta"})
        if not datastore.apply_problem_edit(pid, payload):
            return jsonify({"error": "Problem not found"})
        return jsonify({"success": True})

    @app.post("/api/problem/delete")
    def api_delete_problem() -> Any:
        if not g.user or not g.user.get("is_admin"):
            return jsonify({"error": "Not authorized"})
        try:
            pid = int(request.form.get("pid", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid problem"})
        try:
            datastore.delete_problem(pid)
        except ValueError as exc:
            return jsonify({"error": str(exc)})
        return jsonify({"success": True})

    @app.post("/api/problem/meta")
    def api_update_problem_meta() -> Any:
        user, error = api_user_guard()
        if error:
            return jsonify(error)
        try:
            pid = int(request.form.get("pid", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid problem"})
        problem = datastore.get_problem(pid)
        if not problem:
            return jsonify({"error": "Problem not found"})
        if not datastore.can_user_edit_problem_meta(user, pid):
            return jsonify({"error": "Not authorized"})
        tags_raw = request.form.get("tags", "")
        knowledge = request.form.get("knowledge", "").strip() or None
        tags: List[str] = []
        if tags_raw:
            for piece in tags_raw.split(","):
                name = piece.strip()
                if name and name not in tags:
                    tags.append(name)
        datastore.update_problem_meta(pid, tags, knowledge)
        return jsonify({"success": True, "tags": tags, "knowledge": knowledge})

    @app.post("/api/delete")
    def api_delete_vote() -> Any:
        if not g.user or not g.user.get("is_admin"):
            return jsonify({"error": "Not authorized"})
        try:
            vote_id = int(request.form.get("vid", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid vote"})
        if datastore.mark_vote_deleted(vote_id):
            return jsonify({"success": True})
        return jsonify({"error": "Vote not found"})

    @app.post("/api/report")
    def api_report_vote() -> Any:
        user, error = api_user_guard()
        if error:
            return jsonify(error)
        try:
            vote_id = int(request.form.get("vid", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid vote"})
        success, error_message = datastore.report_vote(vote_id, user["id"])
        if not success:
            return jsonify({"error": error_message or "Unable to report"})
        return jsonify({"success": True})

    @app.get("/api/votes")
    def api_votes() -> Any:
        auth_user, error = api_user_guard()
        if error:
            return jsonify(error)
        try:
            problem_id = int(request.args.get("pid", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid problem"})
        problem = datastore.get_problem(problem_id)
        if not problem:
            return jsonify({"error": "Problem not found"})
        avg_thinking = float(problem.get("avg_thinking") or problem.get("avg_difficulty") or 0)
        avg_implementation = float(problem.get("avg_implementation") or problem.get("avg_difficulty") or 0)
        avg_overall = float(problem.get("avg_difficulty") or 0)
        avg_quality = float(problem.get("avg_quality") or 0)
        is_admin = bool(g.user and g.user.get("is_admin"))
        rows = []
        for vote in datastore.list_votes_for_problem(problem_id):
            if vote.get("deleted"):
                continue
            if not is_admin and not vote.get("public"):
                continue
            vote_user = datastore.find_user_by_id(vote["user_id"])
            if not vote_user:
                continue
            thinking = vote.get("thinking")
            implementation = vote.get("implementation")
            overall = vote.get("overall") or vote.get("difficulty")
            quality_val = vote.get("quality")
            rows.append({
                "id": vote["id"],
                "thinking": thinking,
                "thinking_delta": round((thinking or 0) - avg_thinking, 2) if thinking is not None else None,
                "implementation": implementation,
                "implementation_delta": round((implementation or 0) - avg_implementation, 2) if implementation is not None else None,
                "difficulty": overall,
                "difficulty_delta": round((overall or 0) - avg_overall, 2) if overall is not None else None,
                "quality": quality_val,
                "quality_delta": round((quality_val or 0) - avg_quality, 2) if quality_val is not None else None,
                "comment": vote.get("comment", ""),
                "deleted": vote.get("deleted", False),
                "accepted": vote.get("accepted", False),
                "score": vote.get("score", 0),
                "user_id": vote_user["id"],
                "username": vote_user["username"],
                "public": bool(vote.get("public")),
                "created_at": vote.get("created_at", 0),
            })
        return jsonify({
            "problem": {"id": problem_id, "title": problem["title"], "url": problem.get("url", "")},
            "votes": rows,
        })
