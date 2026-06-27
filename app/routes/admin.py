from flask import render_template, jsonify, abort, request, redirect, url_for
from flask_login import login_required, current_user

from app import db
from app.models import User, Friendship, Event, MeetingRequest, EventParticipant
from app.helpers import (
    pending_count,
    admin_required,
    is_bootstrap_admin,
    platform_admin_count,
)
from app.utils import STATUS_PENDING, STATUS_CONFIRMED, STATUS_REJECTED, STATUS_CANCELLED
from app.time_utils import format_month_year, user_timezone, utcnow
from app.routes import bp


def _count_meetings_by_status(participations):
    counts = {"pending": 0, "confirmed": 0, "rejected": 0, "cancelled": 0, "total": 0}
    for p in participations:
        req = p.event.request
        sid = req.status_id if req else p.status_id
        counts["total"] += 1
        if sid == STATUS_PENDING:
            counts["pending"] += 1
        elif sid == STATUS_CONFIRMED:
            counts["confirmed"] += 1
        elif sid == STATUS_REJECTED:
            counts["rejected"] += 1
        elif sid == STATUS_CANCELLED:
            counts["cancelled"] += 1
    return counts


@bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    members = User.query.order_by(User.username).all()
    bootstrap = {u.id for u in members if is_bootstrap_admin(u)}
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    all_requests = (
        MeetingRequest.query
        .join(Event, Event.id == MeetingRequest.event_id)
        .filter(Event.start_datetime >= month_start)
        .all()
    )
    platform_counts = {
        "pending": sum(1 for r in all_requests if r.status_id == STATUS_PENDING),
        "confirmed": sum(1 for r in all_requests if r.status_id == STATUS_CONFIRMED),
        "rejected": sum(1 for r in all_requests if r.status_id == STATUS_REJECTED),
        "cancelled": sum(1 for r in all_requests if r.status_id == STATUS_CANCELLED),
        "total": len(all_requests),
    }

    my_participations = (
        EventParticipant.query
        .join(Event, Event.id == EventParticipant.event_id)
        .filter(
            EventParticipant.user_id == current_user.id,
            Event.event_type == "meeting",
            Event.start_datetime >= month_start,
        )
        .all()
    )

    platform_stats = {
        "users": User.query.count(),
        "admins": platform_admin_count(),
        "friendships": Friendship.query.filter_by(status="accepted").count(),
        "pending_friend_requests": Friendship.query.filter_by(status="pending").count(),
        "meetings_month": platform_counts["total"],
        "pending_requests": MeetingRequest.query.filter_by(status_id=STATUS_PENDING).count(),
    }
    return render_template(
        "admin_users.html",
        members=members,
        bootstrap_ids=bootstrap,
        platform_stats=platform_stats,
        platform_counts=platform_counts,
        my_counts=_count_meetings_by_status(my_participations),
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
