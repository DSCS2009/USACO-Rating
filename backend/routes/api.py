"""API route registration."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

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
            if datastore.problems_by_type:
                payload = next(iter(datastore.problems_by_type.values()))
            else:
                payload = {"type": {"id": type_id, "name": ""}, "problems": []}
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
        response = {
            "title": problem["title"],
            "url": problem.get("url", ""),
            "contest": problem.get("contest", ""),
            "description": problem.get("description", ""),
            "difficulty": existing["difficulty"] if existing else int(problem.get("avg_difficulty") or 2000),
            "quality": existing["quality"] if existing else round(float(problem.get("avg_quality") or 3.0), 2),
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
            difficulty = int(request.form.get("diff", 0))
            quality = float(request.form.get("qual", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid input"})
        comment = request.form.get("comment", "")
        make_public = request.form.get("public") in {"true", "True", "1", "on", "yes"}
        if not (800 <= difficulty <= 3500 and 0 <= quality <= 5):
            return jsonify({"error": "Out of range"})
        problem = datastore.get_problem(problem_id)
        if not problem:
            return jsonify({"error": "Problem not found"})
        datastore.upsert_vote(user["id"], problem_id, difficulty, quality, comment, make_public)
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
        datastore.report_vote(vote_id, user["id"])
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
        avg_diff = float(problem.get("avg_difficulty") or 0)
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
            rows.append({
                "id": vote["id"],
                "difficulty": vote["difficulty"],
                "difficulty_delta": round(vote["difficulty"] - avg_diff, 2),
                "quality": vote["quality"],
                "quality_delta": round(vote["quality"] - avg_quality, 2),
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
