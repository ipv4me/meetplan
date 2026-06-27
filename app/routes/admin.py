from flask import render_template, jsonify, abort, request
from flask_login import login_required, current_user

from app import db
from app.models import User, Friendship, Event, MeetingRequest
from app.helpers import (
    pending_count,
    admin_required,
    is_bootstrap_admin,
    platform_admin_count,
)
from app.utils import STATUS_PENDING, STATUS_CONFIRMED, STATUS_REJECTED, STATUS_CANCELLED
from app.time_utils import utcnow
from app.routes import bp


@bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    members = User.query.order_by(User.username).all()
    bootstrap = {u.id for u in members if is_bootstrap_admin(u)}
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    platform_stats = {
        "users": User.query.count(),
        "admins": platform_admin_count(),
        "friendships": Friendship.query.filter_by(status="accepted").count(),
        "meetings_month": (
            MeetingRequest.query
            .join(Event, Event.id == MeetingRequest.event_id)
            .filter(Event.start_datetime >= month_start)
            .count()
        ),
        "pending_requests": MeetingRequest.query.filter_by(status_id=STATUS_PENDING).count(),
    }
    return render_template(
        "admin_users.html",
        members=members,
        bootstrap_ids=bootstrap,
        platform_stats=platform_stats,
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

    if is_bootstrap_admin(user) and role != "admin":
        return jsonify({"ok": False, "error": "Нельзя снять права владельца"}), 403

    if user.id == current_user.id and role == "member":
        if platform_admin_count() <= 1:
            return jsonify({"ok": False, "error": "Должен остаться хотя бы один администратор"}), 403

    if role == "member" and user.role == "admin":
        if platform_admin_count() <= 1:
            return jsonify({"ok": False, "error": "Должен остаться хотя бы один администратор"}), 403

    user.role = role
    db.session.commit()
    return jsonify({"ok": True, "role": user.role, "is_admin": user.is_admin})
