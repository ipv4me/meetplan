from flask import render_template, jsonify, abort, request
from flask_login import login_required, current_user

from app import db
from app.models import User
from app.helpers import (
    pending_count,
    admin_required,
    is_bootstrap_admin,
    admin_count,
)
from app.routes import bp


@bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    org_id = current_user.organization_id
    q = User.query.order_by(User.username)
    if org_id:
        q = q.filter_by(organization_id=org_id)
    members = q.all()
    bootstrap = {u.id for u in members if is_bootstrap_admin(u)}
    return render_template(
        "admin_users.html",
        members=members,
        bootstrap_ids=bootstrap,
        pending_count=pending_count(),
    )


@bp.route("/api/admin/users/<int:user_id>/role", methods=["POST"])
@login_required
@admin_required
def api_set_user_role(user_id):
    data = request.get_json() or {}
    role = data.get("role")
    if role not in ("admin", "member"):
        return jsonify({"ok": False, "error": "Некорректная роль"}), 400

    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if current_user.organization_id and user.organization_id != current_user.organization_id:
        abort(403)

    if is_bootstrap_admin(user) and role != "admin":
        return jsonify({"ok": False, "error": "Нельзя снять права владельца"}), 403

    if user.id == current_user.id and role == "member":
        org_id = current_user.organization_id
        if admin_count(org_id) <= 1:
            return jsonify({"ok": False, "error": "Должен остаться хотя бы один администратор"}), 403

    if role == "member" and user.role == "admin":
        org_id = user.organization_id
        if admin_count(org_id) <= 1:
            return jsonify({"ok": False, "error": "Должен остаться хотя бы один администратор"}), 403

    user.role = role
    db.session.commit()
    return jsonify({"ok": True, "role": user.role, "is_admin": user.is_admin})
