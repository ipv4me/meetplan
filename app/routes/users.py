from flask import render_template, abort, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import User
from app.helpers import pending_count, colleagues_query, ensure_colleague, USERS_PER_PAGE
from app.services.scheduling import mutual_free_slots
from app.routes import bp


@bp.route("/users")
@login_required
def users():
    page = request.args.get("page", 1, type=int)
    pagination = colleagues_query().paginate(page=page, per_page=USERS_PER_PAGE, error_out=False)
    return render_template(
        "users.html",
        users=pagination.items,
        pagination=pagination,
        pending_count=pending_count(),
    )


@bp.route("/users/<int:user_id>/calendar")
@login_required
def user_calendar(user_id):
    user = ensure_colleague(user_id)
    return render_template(
        "user_calendar.html",
        viewed_user=user,
        pending_count=pending_count(),
    )


@bp.route("/free-time", methods=["GET"])
@login_required
def free_time():
    others = colleagues_query().all()
    selected_id = request.args.get("user", type=int)
    slots = []
    selected_user = None
    if selected_id:
        selected_user = ensure_colleague(selected_id)
        if selected_user:
            slots = mutual_free_slots(current_user.id, selected_id)
    return render_template(
        "free_time.html",
        users=others,
        selected_user=selected_user,
        slots=slots,
        pending_count=pending_count(),
    )


@bp.route("/api/free-time/<int:user_id>")
@login_required
def api_free_time(user_id):
    ensure_colleague(user_id)
    return jsonify({"ok": True, "slots": mutual_free_slots(current_user.id, user_id)})


@bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html", pending_count=pending_count())
