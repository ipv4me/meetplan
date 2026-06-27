from flask import render_template, abort, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.models import User
from app.helpers import pending_count, friends_query, ensure_friend, USERS_PER_PAGE
from app.friends_service import (
    accept_friendship,
    create_friend_request,
    respond_friend_request,
    cancel_friend_request,
    suggest_users_for_friend,
    pending_incoming,
    pending_outgoing,
    set_friend_shares_details,
    hide_details_map,
)
from app.services.scheduling import mutual_free_slots
from app.routes import bp


@bp.route("/friends")
@login_required
def friends():
    current_user.ensure_invite_token()
    db.session.commit()
    invite_url = url_for("main.friends_join", token=current_user.invite_token, _external=True)
    page = request.args.get("page", 1, type=int)
    pagination = friends_query().paginate(page=page, per_page=USERS_PER_PAGE, error_out=False)
    return render_template(
        "friends.html",
        users=pagination.items,
        pagination=pagination,
        invite_url=invite_url,
        incoming=pending_incoming(current_user.id),
        outgoing=pending_outgoing(current_user.id),
        hide_details=hide_details_map(current_user.id),
        hide_calendar_globally=current_user.hide_calendar_details_from_friends,
        pending_count=pending_count(),
    )


@bp.route("/users")
@login_required
def users():
    return redirect(url_for("main.friends"))


@bp.route("/friends/join/<token>")
@login_required
def friends_join(token):
    owner = User.query.filter_by(invite_token=token).first()
    if owner is None:
        flash("Ссылка-приглашение недействительна.", "warning")
        return redirect(url_for("main.friends"))
    if owner.id == current_user.id:
        flash("Это ваша собственная ссылка.", "info")
        return redirect(url_for("main.friends"))
    _, err = accept_friendship(owner.id, current_user.id, source="invite")
    if err:
        flash(err, "warning")
    else:
        flash(f"Вы добавили {owner.display_name} в друзья.", "success")
    return redirect(url_for("main.friends"))


@bp.route("/api/friends/suggest")
@login_required
def api_friend_suggest():
    q = request.args.get("q", "")
    users = suggest_users_for_friend(q, current_user.id)
    return jsonify({"ok": True, "users": users})


@bp.route("/api/friends/request", methods=["POST"])
@login_required
def api_friend_request():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "error": "Выберите пользователя"}), 400
    target = db.session.get(User, int(user_id))
    if target is None:
        return jsonify({"ok": False, "error": "Пользователь не найден"}), 404
    if target.id == current_user.id:
        return jsonify({"ok": False, "error": "Нельзя добавить себя"}), 400
    _, err = create_friend_request(current_user.id, target.id)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "display_name": target.display_name})


@bp.route("/api/friends/requests/<int:friendship_id>/accept", methods=["POST"])
@login_required
def api_friend_accept(friendship_id):
    row, err = respond_friend_request(friendship_id, current_user.id, accept=True)
    if err:
        return jsonify({"ok": False, "error": err}), 404
    other = row.requester
    return jsonify({"ok": True, "display_name": other.display_name})


@bp.route("/api/friends/requests/<int:friendship_id>/reject", methods=["POST"])
@login_required
def api_friend_reject(friendship_id):
    _, err = respond_friend_request(friendship_id, current_user.id, accept=False)
    if err:
        return jsonify({"ok": False, "error": err}), 404
    return jsonify({"ok": True})


@bp.route("/api/friends/requests/<int:friendship_id>/cancel", methods=["POST"])
@login_required
def api_friend_cancel(friendship_id):
    _, err = cancel_friend_request(friendship_id, current_user.id)
    if err:
        return jsonify({"ok": False, "error": err}), 404
    return jsonify({"ok": True})


@bp.route("/api/friends/hide-calendar-details", methods=["POST"])
@login_required
def api_hide_calendar_details():
    data = request.get_json() or {}
    if "hide" not in data:
        return jsonify({"ok": False, "error": "Укажите hide"}), 400
    current_user.hide_calendar_details_from_friends = bool(data["hide"])
    db.session.commit()
    return jsonify({"ok": True, "hide": current_user.hide_calendar_details_from_friends})


@bp.route("/api/friends/<int:friend_id>/share-details", methods=["POST"])
@login_required
def api_friend_share_details(friend_id):
    ensure_friend(friend_id)
    data = request.get_json() or {}
    if "share" not in data:
        return jsonify({"ok": False, "error": "Укажите share"}), 400
    _, err = set_friend_shares_details(current_user.id, friend_id, data["share"])
    if err:
        return jsonify({"ok": False, "error": err}), 404
    return jsonify({"ok": True, "share": bool(data["share"])})


@bp.route("/users/<int:user_id>/calendar")
@login_required
def user_calendar(user_id):
    user = ensure_friend(user_id)
    return render_template(
        "user_calendar.html",
        viewed_user=user,
        pending_count=pending_count(),
    )


@bp.route("/free-time", methods=["GET"])
@login_required
def free_time():
    others = friends_query().all()
    selected_id = request.args.get("user", type=int)
    slots = []
    selected_user = None
    if selected_id:
        selected_user = ensure_friend(selected_id)
        if selected_user:
            slots = mutual_free_slots(current_user.id, selected_id, viewer=current_user)
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
    ensure_friend(user_id)
    return jsonify({"ok": True, "slots": mutual_free_slots(current_user.id, user_id, viewer=current_user)})


@bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html", pending_count=pending_count())
