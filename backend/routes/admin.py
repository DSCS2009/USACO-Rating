"""Admin-facing route registration."""

from __future__ import annotations

import json
from typing import Any

from flask import abort, flash, g, redirect, render_template, request, session, url_for

from ..auth import require_admin, validate_csrf
from ..datastore import DataStore


def register_admin_routes(app) -> None:
    datastore: DataStore = app.config["DATASTORE"]

    @app.route("/admin")
    def admin_dashboard() -> Any:
        require_admin()
        stats = {
            "total_users": len(datastore.store.get("users", [])),
            "total_problems": len(datastore.problem_map),
            "total_votes": len(datastore.store.get("votes", [])),
        }
        announcements = datastore.list_announcements()
        users = datastore.store.get("users", [])
        pending_users = [u for u in users if not u.get("approved")]
        active_users = [u for u in users if u.get("approved")]
        active_users.sort(key=lambda u: (not u.get("is_admin"), u.get("username", "")))
        courses = datastore.list_types()
        course_contests = {course["id"]: datastore.list_course_contests(course["id"]) for course in courses}
        custom_courses = [course for course in courses if course["id"] in datastore.custom_types]
        custom_course_ids = {course["id"] for course in custom_courses}
        categories = datastore.list_categories()
        course_category_map = {
            course["id"]: datastore.get_category_ids_for_course(course["id"])
            for course in courses
        }
        category_usage = {
            category["id"]: sum(1 for ids in course_category_map.values() if category["id"] in ids)
            for category in categories
        }
        return render_template(
            "admin.html",
            stats=stats,
            announcements=announcements,
            types=courses,
            course_contests=course_contests,
            custom_course_ids=custom_course_ids,
            categories=categories,
            course_category_map=course_category_map,
            category_usage=category_usage,
            pending_users=pending_users,
            active_users=active_users,
            active_page="admin",
        )

    @app.post("/admin/announcement")
    def create_announcement() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        pinned = bool(request.form.get("pinned"))
        if not (title and content):
            flash("请填写标题和内容", "error")
        else:
            datastore.create_announcement(title, content, pinned)
            flash("公告已发布", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/announcement/<int:announcement_id>/delete")
    def delete_announcement(announcement_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.delete_announcement(announcement_id):
            flash("公告已删除", "info")
        else:
            flash("公告不存在", "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/problem")
    def create_problem() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            type_id = int(request.form.get("type_id", "0"))
        except ValueError:
            type_id = 0
        payload = {
            "type": type_id,
            "contest": request.form.get("contest", "").strip(),
            "title": request.form.get("title", "").strip(),
            "url": request.form.get("url", "").strip(),
            "description": request.form.get("description", "").strip(),
        }
        setter_json = request.form.get("setter_json", "").strip()
        source_json = request.form.get("source_json", "").strip()
        meta_json = request.form.get("meta_json", "").strip()
        if setter_json:
            try:
                payload["setter"] = json.loads(setter_json)
            except json.JSONDecodeError:
                flash("出题人 JSON 无法解析", "error")
                return redirect(url_for("admin_dashboard"))
        if source_json:
            try:
                payload["source"] = json.loads(source_json)
            except json.JSONDecodeError:
                flash("来源 JSON 无法解析", "error")
                return redirect(url_for("admin_dashboard"))
        if meta_json:
            try:
                payload["meta"] = json.loads(meta_json)
            except json.JSONDecodeError:
                flash("Meta JSON 无法解析", "error")
                return redirect(url_for("admin_dashboard"))
        if not payload["title"]:
            flash("题目名称不能为空", "error")
            return redirect(url_for("admin_dashboard"))
        datastore.create_problem(payload)
        flash("题目已添加", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/course")
    def admin_create_course() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        name = request.form.get("name", "").strip()
        category_ids = request.form.getlist("category_ids")
        try:
            datastore.create_course(name, category_ids)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("课程已创建", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/course/delete")
    def admin_delete_course() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            type_id = int(request.form.get("type_id", "0"))
        except (TypeError, ValueError):
            flash("请选择要删除的课程", "error")
            return redirect(url_for("admin_dashboard"))
        if datastore.delete_course(type_id):
            flash("课程及其内容已删除", "info")
        else:
            flash("无法删除该课程", "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/course/contest")
    def admin_create_contest() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            type_id = int(request.form.get("type_id", "0"))
        except (TypeError, ValueError):
            flash("请选择课程", "error")
            return redirect(url_for("admin_dashboard"))
        name = request.form.get("name", "").strip()
        try:
            datastore.create_contest(type_id, name)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("比赛已创建", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/course/contest/delete")
    def admin_delete_contest() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            type_id = int(request.form.get("type_id", "0"))
            contest_id = int(request.form.get("contest_id", "0"))
        except (TypeError, ValueError):
            flash("请选择要删除的比赛", "error")
            return redirect(url_for("admin_dashboard"))
        if datastore.delete_contest(type_id, contest_id):
            flash("比赛已删除", "info")
        else:
            flash("未找到要删除的比赛", "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/course/categories")
    def admin_update_course_categories() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            type_id = int(request.form.get("type_id", "0"))
        except (TypeError, ValueError):
            flash("请选择课程", "error")
            return redirect(url_for("admin_dashboard"))
        category_ids = request.form.getlist("category_ids")
        try:
            datastore.set_course_categories(type_id, category_ids)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("课程分类已更新", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/category")
    def admin_create_category() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        name = request.form.get("name", "").strip()
        try:
            datastore.create_category(name)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("分类已创建", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/category/delete")
    def admin_delete_category() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            category_id = int(request.form.get("category_id", "0"))
        except (TypeError, ValueError):
            flash("请选择要删除的分类", "error")
            return redirect(url_for("admin_dashboard"))
        if datastore.delete_category(category_id):
            flash("分类已删除", "info")
        else:
            flash("未找到该分类", "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/approve")
    def admin_approve_user(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.approve_user(user_id):
            flash("账户已通过审核", "success")
        else:
            flash("未找到该账户", "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/reject")
    def admin_reject_user(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.reject_user(user_id):
            flash("已拒绝并移除该账户", "info")
        else:
            flash("未找到该账户", "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/set-admin")
    def admin_set_role(user_id: int) -> Any:
        admin_user = require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        make_admin = request.form.get("is_admin") == "1"
        if datastore.set_admin(user_id, make_admin):
            if user_id == admin_user["id"] and not make_admin:
                session.pop("user_id", None)
                flash("已取消管理员身份，请重新登录。", "info")
                return redirect(url_for("login"))
            flash("权限已更新", "success")
        else:
            flash("更新失败，未找到用户", "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/ban")
    def admin_ban_user(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.set_banned(user_id, True):
            flash("账户已封禁", "warning")
        else:
            flash("操作失败，未找到用户", "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/unban")
    def admin_unban_user(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.set_banned(user_id, False):
            flash("账户已解除封禁", "success")
        else:
            flash("操作失败，未找到用户", "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/clear-votes")
    def admin_clear_votes(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        cleared = datastore.clear_votes_for_user(user_id)
        if cleared:
            flash(f"已清除 {cleared} 条评分记录", "info")
        else:
            flash("该用户暂无可清除的评分", "warning")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/password")
    def admin_reset_user_password() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            user_id = int(request.form.get("user_id", "0"))
        except (TypeError, ValueError):
            flash("请选择用户", "error")
            return redirect(url_for("admin_dashboard"))
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        if not password or not password_confirm:
            flash("请填写新密码", "error")
            return redirect(url_for("admin_dashboard"))
        if password != password_confirm:
            flash("两次输入的密码不一致", "error")
            return redirect(url_for("admin_dashboard"))
        user = datastore.find_user_by_id(user_id)
        if not user:
            flash("未找到用户", "error")
            return redirect(url_for("admin_dashboard"))
        datastore.update_password(user, password)
        flash("密码已更新", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/problem/<int:problem_id>/delete-votes")
    def admin_delete_problem_votes(problem_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        vote_ids = request.form.getlist("vote_ids")
        deleted = datastore.mark_votes_deleted_bulk(vote_ids)
        if deleted:
            flash(f"已删除 {deleted} 条评分", "info")
        else:
            flash("请选择要删除的评分", "warning")
        return redirect(url_for("problem_detail", problem_id=problem_id))
