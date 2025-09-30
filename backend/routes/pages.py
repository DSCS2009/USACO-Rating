"""Page routes registration."""

from __future__ import annotations

from typing import Any

from flask import abort, flash, g, redirect, render_template, request, session, url_for

from ..auth import validate_csrf
from ..datastore import DataStore


def register_page_routes(app) -> None:
    datastore: DataStore = app.config["DATASTORE"]

    @app.route("/")
    def index() -> str:
        groups = datastore.list_type_groups()
        return render_template("index.html", course_groups=groups, active_page="problems")

    @app.route("/register", methods=["GET", "POST"])
    def register() -> Any:
        if request.method == "POST":
            if not validate_csrf(request.form.get("csrf_token")):
                abort(400, description="Invalid CSRF token")
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            luoguid = request.form.get("luoguid", "").strip()
            info = request.form.get("info", "").strip()
            read = request.form.get("read")
            if not (username and password and luoguid and info and read):
                flash("请完整填写所有字段", "error")
            else:
                try:
                    datastore.register_user(username, password, luoguid, info)
                except ValueError as exc:
                    flash(str(exc), "error")
                else:
                    flash("注册成功，请等待管理员审核后再登录。", "success")
                    return redirect(url_for("login"))
        return render_template("register.html", active_page="register")

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Any:
        if request.method == "POST":
            if not validate_csrf(request.form.get("csrf_token")):
                abort(400, description="Invalid CSRF token")
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = datastore.find_user_by_username(username) if username else None
            if not user or not datastore.verify_user_password(user, password):
                flash("用户名或密码错误", "error")
            elif not user.get("approved"):
                flash("账户尚未通过审核，无法登录。", "error")
            elif user.get("banned"):
                flash("账户已被封禁，请联系管理员。", "error")
            else:
                session["user_id"] = user["id"]
                flash("登录成功", "success")
                return redirect(url_for("index"))
        return render_template("login.html", active_page="login")

    @app.post("/logout")
    def logout() -> Any:
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        session.pop("user_id", None)
        flash("已退出登录", "info")
        return redirect(url_for("index"))

    @app.route("/legal")
    def legal() -> str:
        return render_template("legal.html", active_page="legal")

    @app.route("/reset", methods=["GET", "POST"])
    def reset_password() -> Any:
        abort(404)

    @app.route("/profile/<int:user_id>")
    def profile(user_id: int) -> str:
        user = datastore.find_user_by_id(user_id)
        if not user:
            abort(404)
        viewer = getattr(g, "user", None)
        is_admin = bool(viewer and viewer.get("is_admin"))
        is_profile_owner = bool(viewer and viewer.get("id") == user_id)
        can_view_private = is_admin or is_profile_owner
        votes = [
            vote
            for vote in datastore.store.get("votes", [])
            if vote["user_id"] == user_id and not vote.get("deleted")
        ]
        votes.sort(key=lambda x: -x.get("created_at", 0))
        enriched = []
        difficulty_deltas = []
        quality_deltas = []
        thinking_deltas = []
        implementation_deltas = []
        for vote in votes:
            if not can_view_private and not vote.get("public"):
                continue
            problem = datastore.get_problem(vote["problem_id"])
            if not problem:
                continue
            avg_difficulty = problem.get("avg_difficulty")
            if avg_difficulty is not None:
                difficulty_deltas.append(vote["difficulty"] - float(avg_difficulty))
            avg_quality = problem.get("avg_quality")
            if avg_quality is not None:
                quality_deltas.append(vote["quality"] - float(avg_quality))
            avg_thinking = problem.get("avg_thinking") or avg_difficulty
            if avg_thinking is not None and vote.get("thinking") is not None:
                thinking_deltas.append(vote["thinking"] - float(avg_thinking))
            avg_implementation = problem.get("avg_implementation") or avg_difficulty
            if avg_implementation is not None and vote.get("implementation") is not None:
                implementation_deltas.append(vote["implementation"] - float(avg_implementation))
            enriched.append({
                "problem": {"id": problem["id"], "title": problem["title"]},
                "thinking": vote.get("thinking"),
                "implementation": vote.get("implementation"),
                "difficulty": vote["difficulty"],
                "quality": vote["quality"],
                "comment": vote.get("comment", ""),
                "public": vote.get("public", False),
                "created_at": vote.get("created_at", 0),
            })
        if enriched:
            last_vote_ts = enriched[0]["created_at"]
        else:
            last_vote_ts = None
        avg_diff_delta = sum(difficulty_deltas) / len(difficulty_deltas) if difficulty_deltas else None
        avg_quality_delta = sum(quality_deltas) / len(quality_deltas) if quality_deltas else None
        avg_thinking_delta = sum(thinking_deltas) / len(thinking_deltas) if thinking_deltas else None
        avg_impl_delta = sum(implementation_deltas) / len(implementation_deltas) if implementation_deltas else None
        stats = {
            "total_votes": len(enriched),
            "avg_thinking_delta": avg_thinking_delta,
            "avg_implementation_delta": avg_impl_delta,
            "avg_difficulty_delta": avg_diff_delta,
            "avg_quality_delta": avg_quality_delta,
            "last_vote": last_vote_ts,
        }
        return render_template(
            "profile.html",
            profile_user=user,
            votes=enriched,
            stats=stats,
            active_page="profile" if g.user and g.user["id"] == user_id else None,
        )

    @app.route("/problem/<int:problem_id>")
    def problem_detail(problem_id: int) -> str:
        problem = datastore.get_problem(problem_id)
        if not problem:
            abort(404)
        is_admin = bool(g.user and g.user.get("is_admin"))
        public_votes = []
        admin_votes = []
        for vote in datastore.list_votes_for_problem(problem_id):
            if vote.get("deleted"):
                continue
            user = datastore.find_user_by_id(vote["user_id"])
            if not user:
                continue
            entry = {
                "id": vote["id"],
                "user": {"id": user["id"], "username": user["username"]},
                "thinking": vote.get("thinking"),
                "implementation": vote.get("implementation"),
                "difficulty": vote["difficulty"],
                "quality": vote["quality"],
                "comment": vote.get("comment", ""),
                "created_at": vote.get("created_at", 0),
                "public": bool(vote.get("public")),
            }
            if entry["public"]:
                public_votes.append(entry)
            if is_admin or entry["public"]:
                admin_votes.append(entry)
        public_votes.sort(key=lambda x: -x["created_at"])
        admin_votes.sort(key=lambda x: -x["created_at"])
        if problem.get("meta", {}).get("stats"):
            stats = dict(problem["meta"]["stats"])
            submit = stats.get("submit_count", 0) or 0
            ac = stats.get("ac_count", 0) or 0
            stats["pass_rate"] = round((ac / submit * 100) if submit else 0, 2)
            problem["meta"]["stats"] = stats
        votes_for_display = admin_votes if is_admin else public_votes
        return render_template(
            "problem.html",
            problem=problem,
            votes=votes_for_display,
            public_votes=public_votes,
            is_admin=is_admin,
            active_page="problems",
        )
