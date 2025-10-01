"""Admin-facing route registration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import abort, flash, g, redirect, render_template, request, session, url_for

from ..auth import require_admin, validate_csrf
from ..datastore import DataStore


def register_admin_routes(app) -> None:
    datastore: DataStore = app.config["DATASTORE"]

    def _global_default_info() -> Any:
        default_id = datastore.get_global_default_course_id()
        course = datastore.types.get(default_id) if default_id is not None else None
        course_name = course.get("name") if course else None
        return default_id, course_name

    @app.route("/admin")
    def admin_dashboard() -> Any:
        require_admin()
        return redirect(url_for("admin_overview"))

    @app.route("/admin/overview")
    def admin_overview() -> Any:
        require_admin()
        stats = {
            "total_users": len(datastore.store.get("users", [])),
            "total_problems": len(datastore.problem_map),
            "total_votes": len(datastore.store.get("votes", [])),
        }
        announcements = datastore.list_announcements()
        courses = datastore.list_types()
        default_id, default_name = _global_default_info()
        return render_template(
            "admin/overview.html",
            stats=stats,
            announcements=announcements,
            types=courses,
            global_default_course_id=default_id,
            global_default_course_name=default_name,
            admin_active="overview",
        )

    @app.route("/admin/users")
    def admin_users() -> Any:
        require_admin()
        users = datastore.store.get("users", [])
        pending_users = [u for u in users if not u.get("approved")]
        active_users = [u for u in users if u.get("approved")]
        pending_users.sort(key=lambda u: u.get("created_at", 0))
        active_users.sort(key=lambda u: (not u.get("is_admin"), u.get("username", "")))
        courses = datastore.list_types()
        default_id, default_name = _global_default_info()
        return render_template(
            "admin/users.html",
            pending_users=pending_users,
            active_users=active_users,
            types=courses,
            global_default_course_id=default_id,
            global_default_course_name=default_name,
            admin_active="users",
        )

    @app.route("/admin/courses")
    def admin_courses() -> Any:
        require_admin()
        courses = datastore.list_types()
        categories = datastore.list_categories()
        course_category_map = {
            course["id"]: datastore.get_category_ids_for_course(course["id"])
            for course in courses
        }
        category_usage = {
            category["id"]: sum(1 for ids in course_category_map.values() if category["id"] in ids)
            for category in categories
        }
        course_contests = {course["id"]: datastore.list_course_contests(course["id"]) for course in courses}
        custom_course_ids = {course["id"] for course in courses if course["id"] in datastore.custom_types}
        default_id, default_name = _global_default_info()
        return render_template(
            "admin/courses.html",
            types=courses,
            categories=categories,
            course_category_map=course_category_map,
            category_usage=category_usage,
            course_contests=course_contests,
            custom_course_ids=custom_course_ids,
            global_default_course_id=default_id,
            global_default_course_name=default_name,
            admin_active="courses",
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
        return redirect(url_for("admin_overview"))

    @app.post("/admin/announcement/<int:announcement_id>/delete")
    def delete_announcement(announcement_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.delete_announcement(announcement_id):
            flash("公告已删除", "info")
        else:
            flash("公告不存在", "error")
        return redirect(url_for("admin_overview"))

    @app.post("/admin/settings/default-course")
    def admin_set_global_default_course() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        raw_course_id = request.form.get("course_id", "").strip()
        try:
            if not raw_course_id:
                datastore.set_global_default_course(None)
                flash("已清除全局默认课程", "info")
            else:
                datastore.set_global_default_course(raw_course_id)
                _, course_name = _global_default_info()
                if course_name:
                    flash(f"全局默认课程已设置为「{course_name}」", "success")
                else:
                    flash("全局默认课程已更新", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_overview"))

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
                return redirect(url_for("admin_courses"))
        if source_json:
            try:
                payload["source"] = json.loads(source_json)
            except json.JSONDecodeError:
                flash("来源 JSON 无法解析", "error")
                return redirect(url_for("admin_courses"))
        if meta_json:
            try:
                payload["meta"] = json.loads(meta_json)
            except json.JSONDecodeError:
                flash("Meta JSON 无法解析", "error")
                return redirect(url_for("admin_courses"))
        if not payload["title"]:
            flash("题目名称不能为空", "error")
            return redirect(url_for("admin_courses"))
        datastore.create_problem(payload)
        flash("题目已添加", "success")
        return redirect(url_for("admin_courses"))

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
        return redirect(url_for("admin_courses"))

    @app.post("/admin/course/delete")
    def admin_delete_course() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            type_id = int(request.form.get("type_id", "0"))
        except (TypeError, ValueError):
            flash("请选择要删除的课程", "error")
            return redirect(url_for("admin_courses"))
        if datastore.delete_course(type_id):
            flash("课程及其内容已删除", "info")
        else:
            flash("无法删除该课程", "error")
        return redirect(url_for("admin_courses"))

    @app.post("/admin/course/contest")
    def admin_create_contest() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            type_id = int(request.form.get("type_id", "0"))
        except (TypeError, ValueError):
            flash("请选择课程", "error")
            return redirect(url_for("admin_courses"))
        name = request.form.get("name", "").strip()
        try:
            datastore.create_contest(type_id, name)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("比赛已创建", "success")
        return redirect(url_for("admin_courses"))

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
            return redirect(url_for("admin_courses"))
        if datastore.delete_contest(type_id, contest_id):
            flash("比赛已删除", "info")
        else:
            flash("未找到要删除的比赛", "error")
        return redirect(url_for("admin_courses"))

    @app.post("/admin/course/categories")
    def admin_update_course_categories() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            type_id = int(request.form.get("type_id", "0"))
        except (TypeError, ValueError):
            flash("请选择课程", "error")
            return redirect(url_for("admin_courses"))
        category_ids = request.form.getlist("category_ids")
        try:
            datastore.set_course_categories(type_id, category_ids)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("课程分类已更新", "success")
        return redirect(url_for("admin_courses"))

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
        return redirect(url_for("admin_courses"))

    @app.post("/admin/category/delete")
    def admin_delete_category() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            category_id = int(request.form.get("category_id", "0"))
        except (TypeError, ValueError):
            flash("请选择要删除的分类", "error")
            return redirect(url_for("admin_courses"))
        if datastore.delete_category(category_id):
            flash("分类已删除", "info")
        else:
            flash("未找到该分类", "error")
        return redirect(url_for("admin_courses"))

    @app.post("/admin/users/<int:user_id>/approve")
    def admin_approve_user(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.approve_user(user_id):
            flash("账户已通过审核", "success")
        else:
            flash("未找到该账户", "error")
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:user_id>/reject")
    def admin_reject_user(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.reject_user(user_id):
            flash("已拒绝并移除该账户", "info")
        else:
            flash("未找到该账户", "error")
        return redirect(url_for("admin_users"))

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
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:user_id>/ban")
    def admin_ban_user(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.set_banned(user_id, True):
            flash("账户已封禁", "warning")
        else:
            flash("操作失败，未找到用户", "error")
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:user_id>/unban")
    def admin_unban_user(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        if datastore.set_banned(user_id, False):
            flash("账户已解除封禁", "success")
        else:
            flash("操作失败，未找到用户", "error")
        return redirect(url_for("admin_users"))

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
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:user_id>/default-course")
    def admin_set_default_course(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        raw_course_id = request.form.get("course_id", "").strip()
        course_id = None
        if raw_course_id:
            try:
                course_id = int(raw_course_id)
            except (TypeError, ValueError):
                flash("请选择有效的课程", "error")
                return redirect(url_for("admin_users"))
        try:
            updated = datastore.set_user_default_course(user_id, course_id)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            if not updated:
                flash("未找到用户", "error")
            else:
                if course_id is None:
                    flash("已改为跟随全局默认课程", "success")
                else:
                    course = datastore.types.get(course_id)
                    course_name = course.get("name") if course else None
                    message = f"默认课程已更新为「{course_name}」" if course_name else "默认课程已更新"
                    flash(message, "success")
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:user_id>/tag-permissions")
    def admin_add_tag_permission(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        permission = request.form.get("permission", "").strip()
        if not permission:
            flash("请输入有效的标签名称", "error")
            return redirect(url_for("admin_users"))
        try:
            if datastore.add_tag_permission(user_id, permission):
                flash("标签权限已添加", "success")
            else:
                flash("用户已拥有该标签权限", "info")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:user_id>/tag-permissions/remove")
    def admin_remove_tag_permission(user_id: int) -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        permission = request.form.get("permission", "").strip()
        if not permission:
            flash("标签名称无效", "error")
            return redirect(url_for("admin_users"))
        if datastore.remove_tag_permission(user_id, permission):
            flash("标签权限已移除", "info")
        else:
            flash("未找到对应的标签权限", "warning")
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/password")
    def admin_reset_user_password() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        try:
            user_id = int(request.form.get("user_id", "0"))
        except (TypeError, ValueError):
            flash("请选择用户", "error")
            return redirect(url_for("admin_users"))
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        if not password or not password_confirm:
            flash("请填写新密码", "error")
            return redirect(url_for("admin_users"))
        if password != password_confirm:
            flash("两次输入的密码不一致", "error")
            return redirect(url_for("admin_users"))
        user = datastore.find_user_by_id(user_id)
        if not user:
            flash("未找到用户", "error")
            return redirect(url_for("admin_users"))
        datastore.update_password(user, password)
        flash("密码已更新", "success")
        return redirect(url_for("admin_users"))

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

    @app.post("/admin/import/legacy")
    def admin_import_legacy() -> Any:
        require_admin()
        if not validate_csrf(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token")
        legacy_dir = Path(app.root_path).parent / "vote"
        users_path = legacy_dir / "user.json"
        votes_path = legacy_dir / "votes.json"
        problems_path = legacy_dir / "problem.txt"
        try:
            summary = datastore.import_legacy_config(
                users_path=users_path,
                votes_path=votes_path,
                problems_path=problems_path,
            )
        except FileNotFoundError:
            flash("未找到 legacy 配置文件", "error")
        except Exception as exc:
            flash(f"导入失败：{exc}", "error")
        else:
            flash(
                "导入完成：新增用户 {users_created}，更新用户 {users_updated}，标签权限更新 {tag_permissions_updated}，新增题目 {problems_created}，"\
                "更新题目 {problems_updated}，导入评分 {votes_imported}，更新评分 {votes_updated}，跳过 {skipped_votes}".format(**summary),
                "success",
            )
        return redirect(url_for("admin_overview"))
