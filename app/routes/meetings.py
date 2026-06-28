from datetime import datetime, timedelta

from flask import render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user

from app import db
from app.models import Event, MeetingRequest, EventParticipant
from app.forms import MeetingForm
from app.utils import status_label, STATUS_PENDING, STATUS_CONFIRMED, STATUS_CANCELLED, STATUS_REJECTED
from app.helpers import pending_count, meeting_user_choices, create_meeting_event, valid_colleague_ids, REQUESTS_PER_PAGE, client_timezone_name
from app.time_utils import combine_user_meeting, utc_to_local, user_timezone, parse_client_datetime, format_dt, utcnow
from app.services.scheduling import find_conflicts
from app.routes import bp


def _render_meeting_form(form, title, exclude_event_id=None):
    return render_template(
        "meeting_form.html",
        form=form,
        form_title=title,
        exclude_event_id=exclude_event_id,
        has_friends=bool(meeting_user_choices()),
    )


def _prefill_meeting_form(form):
    preselect = request.args.get("to", type=int)
    if preselect:
        form.to_user.data = preselect
    date_s = request.args.get("date")
    start_s = request.args.get("start")
    if date_s:
        try:
            form.date.data = datetime.strptime(date_s, "%Y-%m-%d").date()
        except ValueError:
            pass
    if start_s:
        try:
            form.start_time.data = datetime.strptime(start_s, "%H:%M").time()
            end_dt = datetime.combine(form.date.data or utcnow().date(), form.start_time.data)
            form.end_time.data = (end_dt + timedelta(hours=1)).time()
        except ValueError:
            pass


@bp.route("/meeting/new", methods=["GET", "POST"])
@login_required
def new_meeting():
    form = MeetingForm()
    form.to_user.choices = meeting_user_choices()
    if form.validate_on_submit():
        if form.to_user.data == current_user.id:
            flash("Нельзя назначить встречу самому себе.", "danger")
            return redirect(url_for("main.new_meeting"))
        if form.to_user.data not in valid_colleague_ids():
            flash("Выберите друга из списка.", "danger")
            return redirect(url_for("main.new_meeting"))
        start, end = combine_user_meeting(
            form.date.data, form.start_time.data, form.end_time.data, current_user,
            client_timezone_name(),
        )
        conflicts = find_conflicts(
            [current_user.id, form.to_user.data], start, end, viewer_id=current_user.id,
        )
        if conflicts:
            names = ", ".join({c["username"] for c in conflicts})
            flash(f"Конфликт расписания у: {names}. Выберите другое время.", "danger")
            return render_template(
                "meeting_form.html", form=form, form_title="Создать встречу",
                has_friends=bool(meeting_user_choices()),
            )
        create_meeting_event(
            current_user.id, form.to_user.data, form.title.data,
            form.description.data, start, end,
        )
        db.session.commit()
        flash("Запрос на встречу отправлен.", "success")
        return redirect(url_for("main.requests_page"))

    if request.method == "GET":
        _prefill_meeting_form(form)
    return _render_meeting_form(form, "Создать встречу")


@bp.route("/meeting/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit_meeting(event_id):
    ev = db.session.get(Event, event_id)
    if ev is None or ev.created_by != current_user.id or ev.event_type != "meeting":
        abort(404)
    form = MeetingForm()
    form.to_user.choices = meeting_user_choices()
    if request.method == "GET":
        tz = user_timezone(current_user)
        start_local = utc_to_local(ev.start_datetime, tz)
        end_local = utc_to_local(ev.end_datetime, tz)
        form.to_user.data = ev.request.to_user_id if ev.request else None
        form.title.data = ev.title
        form.description.data = ev.description
        form.date.data = start_local.date()
        form.start_time.data = start_local.time()
        form.end_time.data = end_local.time()
    if form.validate_on_submit():
        if form.to_user.data == current_user.id:
            flash("Нельзя назначить встречу самому себе.", "danger")
            return _render_meeting_form(form, "Редактировать встречу", exclude_event_id=ev.id)
        if form.to_user.data not in valid_colleague_ids():
            flash("Выберите друга из списка.", "danger")
            return _render_meeting_form(form, "Редактировать встречу", exclude_event_id=ev.id)
        start, end = combine_user_meeting(
            form.date.data, form.start_time.data, form.end_time.data, current_user,
            client_timezone_name(),
        )
        conflicts = find_conflicts(
            [current_user.id, form.to_user.data], start, end,
            exclude_event_id=ev.id, viewer_id=current_user.id,
        )
        if conflicts:
            names = ", ".join({c["username"] for c in conflicts})
            flash(f"Конфликт расписания у: {names}.", "danger")
            return _render_meeting_form(form, "Редактировать встречу", exclude_event_id=ev.id)
        ev.title = form.title.data
        ev.description = form.description.data
        ev.start_datetime = start
        ev.end_datetime = end
        if ev.request:
            ev.request.to_user_id = form.to_user.data
            ev.request.status_id = STATUS_PENDING
        EventParticipant.query.filter_by(event_id=ev.id).delete()
        db.session.add(EventParticipant(event_id=ev.id, user_id=current_user.id, status_id=STATUS_CONFIRMED))
        db.session.add(EventParticipant(event_id=ev.id, user_id=form.to_user.data, status_id=STATUS_PENDING))
        db.session.commit()
        flash("Встреча обновлена, запрос отправлен повторно.", "success")
        return redirect(url_for("main.calendar"))
    return _render_meeting_form(form, "Редактировать встречу", exclude_event_id=ev.id)


@bp.route("/api/meetings/check-conflicts", methods=["POST"])
@login_required
def api_check_conflicts():
    data = request.get_json() or {}
    try:
        to_user = int(data["to_user"])
        start = parse_client_datetime(data["start"], current_user, client_timezone_name())
        end = parse_client_datetime(data["end"], current_user, client_timezone_name())
        exclude = data.get("exclude_event_id")
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "Некорректные данные"}), 400
    if end <= start:
        return jsonify({"ok": False, "error": "Некорректный интервал"}), 400
    if to_user == current_user.id:
        return jsonify({"ok": False, "error": "Нельзя назначить встречу самому себе"}), 400
    if to_user not in valid_colleague_ids():
        return jsonify({"ok": False, "error": "Пользователь не в списке друзей"}), 400
    conflicts = find_conflicts(
        [current_user.id, to_user], start, end,
        exclude_event_id=int(exclude) if exclude else None,
        viewer_id=current_user.id,
    )
    return jsonify({"ok": True, "conflicts": conflicts})


@bp.route("/api/meetings/<int:event_id>/cancel", methods=["POST"])
@login_required
def api_cancel_meeting(event_id):
    ev = db.session.get(Event, event_id)
    if ev is None or ev.event_type != "meeting" or not ev.request:
        abort(404)
    req = ev.request
    if current_user.id not in (req.from_user_id, req.to_user_id):
        abort(403)
    if req.status_id in (STATUS_CANCELLED, STATUS_REJECTED):
        return jsonify({"ok": True, "label": status_label(req.status_id)})
    req.status_id = STATUS_CANCELLED
    for part in EventParticipant.query.filter_by(event_id=ev.id).all():
        part.status_id = STATUS_CANCELLED
    db.session.commit()
    return jsonify({"ok": True, "status": STATUS_CANCELLED, "label": status_label(STATUS_CANCELLED)})


@bp.route("/api/meetings/<int:event_id>", methods=["DELETE"])
@login_required
def api_delete_meeting(event_id):
    ev = db.session.get(Event, event_id)
    if ev is None or ev.event_type != "meeting" or not ev.request:
        abort(404)
    req = ev.request
    if current_user.id not in (req.from_user_id, req.to_user_id):
        abort(403)
    if req.from_user_id != current_user.id:
        return jsonify({"ok": False, "error": "Удалить встречу может только организатор"}), 403
    EventParticipant.query.filter_by(event_id=ev.id).delete()
    db.session.delete(ev)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/requests")
@login_required
def requests_page():
    inc_page = request.args.get("inc_page", 1, type=int)
    out_page = request.args.get("out_page", 1, type=int)
    incoming_p = (
        MeetingRequest.query
        .filter_by(to_user_id=current_user.id)
        .order_by(MeetingRequest.created_at.desc())
        .paginate(page=inc_page, per_page=REQUESTS_PER_PAGE, error_out=False)
    )
    outgoing_p = (
        MeetingRequest.query
        .filter_by(from_user_id=current_user.id)
        .order_by(MeetingRequest.created_at.desc())
        .paginate(page=out_page, per_page=REQUESTS_PER_PAGE, error_out=False)
    )
    return render_template(
        "requests.html",
        incoming=incoming_p.items,
        outgoing=outgoing_p.items,
        incoming_pagination=incoming_p,
        outgoing_pagination=outgoing_p,
        pending_count=pending_count(),
    )


@bp.route("/api/requests/<int:req_id>/<action>", methods=["POST"])
@login_required
def api_request_action(req_id, action):
    from app.utils import STATUS_REJECTED

    req = db.session.get(MeetingRequest, req_id)
    if req is None or req.to_user_id != current_user.id:
        abort(404)
    if req.status_id != STATUS_PENDING:
        return jsonify({"ok": False, "error": "Запрос уже обработан"}), 409
    if action == "confirm":
        new_status = STATUS_CONFIRMED
    elif action == "reject":
        new_status = STATUS_REJECTED
    else:
        abort(400)

    req.status_id = new_status
    part = EventParticipant.query.filter_by(
        event_id=req.event_id, user_id=current_user.id
    ).first()
    if part:
        part.status_id = new_status
    db.session.commit()
    return jsonify({"ok": True, "status": new_status, "label": status_label(new_status)})


@bp.route("/notifications")
@login_required
def notifications():
    return redirect(url_for("main.requests_page", tab="incoming"))


@bp.route("/api/notifications")
@login_required
def api_notifications():
    pending = (
        MeetingRequest.query
        .filter_by(to_user_id=current_user.id, status_id=STATUS_PENDING)
        .order_by(MeetingRequest.created_at.desc())
        .all()
    )
    items = [
        {
            "id": r.id,
            "from": r.from_user.username,
            "title": r.event.title,
            "when": format_dt(r.event.start_datetime, current_user),
        }
        for r in pending
    ]
    return jsonify({"count": len(items), "items": items})
