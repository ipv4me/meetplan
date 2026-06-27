from datetime import timedelta

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
from app.time_utils import format_month_year, user_timezone, utcnow
from app.routes import bp


def _meeting_counts_for_month(month_start):
    requests = (
        MeetingRequest.query
        .join(Event, Event.id == MeetingRequest.event_id)
        .filter(Event.start_datetime >= month_start)
        .all()
    )
    counts = {"pending": 0, "confirmed": 0, "rejected": 0, "cancelled": 0, "total": len(requests)}
    for req in requests:
        if req.status_id == STATUS_PENDING:
            counts["pending"] += 1
        elif req.status_id == STATUS_CONFIRMED:
            counts["confirmed"] += 1
        elif req.status_id == STATUS_REJECTED:
            counts["rejected"] += 1
        elif req.status_id == STATUS_CANCELLED:
            counts["cancelled"] += 1
    return counts


def _friend_counts():
    """user_id -> число принятых дружб."""
    counts = {}
    rows = Friendship.query.filter_by(status="accepted").all()
    for row in rows:
        counts[row.requester_id] = counts.get(row.requester_id, 0) + 1
        counts[row.addressee_id] = counts.get(row.addressee_id, 0) + 1
    return counts


@bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    members = User.query.order_by(User.username).all()
    bootstrap = {u.id for u in members if is_bootstrap_admin(u)}
    meeting_counts = _meeting_counts_for_month(month_start)
    friend_counts = _friend_counts()

    overview = {
        "users_total": len(members),
        "users_new_week": sum(1 for u in members if u.created_at and u.created_at >= week_start),
        "users_new_month": sum(1 for u in members if u.created_at and u.created_at >= month_start),
        "admins": platform_admin_count(),
        "friendships": Friendship.query.filter_by(status="accepted").count(),
        "pending_friends": Friendship.query.filter_by(status="pending").count(),
        "pending_meetings": MeetingRequest.query.filter_by(status_id=STATUS_PENDING).count(),
    }

    return render_template(
        "admin_users.html",
        members=members,
        bootstrap_ids=bootstrap,
        friend_counts=friend_counts,
        overview=overview,
        meeting_counts=meeting_counts,
        recent_users=User.query.order_by(User.created_at.desc()).limit(6).all(),
        month_label=format_month_year(month_start, user_timezone(current_user)),
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
