from datetime import datetime, timedelta

from flask import render_template, jsonify, abort, request, flash, redirect, url_for
from flask_login import login_required, current_user

from app import db
from app.models import User, Event, MeetingRequest, Task
from app.forms import EventForm
from app.utils import events_for_user, STATUS_PENDING
from app.helpers import (
    pending_count,
    colleagues_query,
    ensure_colleague,
    client_timezone_name,
    validate_title,
)
from app.time_utils import (
    combine_user_meeting,
    utc_to_local,
    parse_client_datetime,
    effective_timezone,
    duration_ok,
)
from app.routes import bp


def _apply_overnight(start, end):
    if end <= start:
        end = end + timedelta(days=1)
    return start, end


@bp.route("/")
@bp.route("/calendar")
@login_required
def calendar():
    others = colleagues_query().all()
    latest_request = (
        MeetingRequest.query
        .filter_by(to_user_id=current_user.id, status_id=STATUS_PENDING)
        .order_by(MeetingRequest.created_at.desc())
        .first()
    )
    my_tasks = (
        Task.query
        .filter_by(user_id=current_user.id)
        .order_by(Task.done, Task.created_at.desc())
        .limit(6)
        .all()
    )
    return render_template(
        "calendar.html",
        pending_count=pending_count(),
        users=others,
        latest_request=latest_request,
        tasks=my_tasks,
    )


@bp.route("/api/events")
@login_required
def api_events():
    return jsonify(events_for_user(current_user.id))


@bp.route("/api/users/<int:user_id>/events")
@login_required
def api_user_events(user_id):
    user = ensure_colleague(user_id)
    return jsonify(events_for_user(user.id, viewer_id=current_user.id))


@bp.route("/api/events", methods=["POST"])
@login_required
def api_create_event():
    data = request.get_json() or {}
    try:
        ok, title = validate_title(data.get("title"))
        if not ok:
            return jsonify({"ok": False, "error": title}), 400
        start = parse_client_datetime(data["start"], current_user, client_timezone_name())
        end = parse_client_datetime(data["end"], current_user, client_timezone_name())
        start, end = _apply_overnight(start, end)
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "Некорректные данные"}), 400
    if not duration_ok(start, end):
        return jsonify({"ok": False, "error": "Длительность не больше 24 часов"}), 400

    ev = Event(
        title=title,
        description=data.get("description", ""),
        start_datetime=start,
        end_datetime=end,
        event_type="personal",
        created_by=current_user.id,
    )
    db.session.add(ev)
    db.session.commit()
    return jsonify({"ok": True, "id": ev.id})


@bp.route("/api/events/<int:event_id>", methods=["DELETE"])
@login_required
def api_delete_event(event_id):
    ev = db.session.get(Event, event_id)
    if ev is None or ev.created_by != current_user.id or ev.event_type != "personal":
        abort(404)
    db.session.delete(ev)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/events/<int:event_id>/reschedule", methods=["POST"])
@login_required
def api_reschedule_event(event_id):
    ev = db.session.get(Event, event_id)
    if ev is None or ev.created_by != current_user.id or ev.event_type != "personal":
        abort(404)
    data = request.get_json() or {}
    try:
        start = parse_client_datetime(data["start"], current_user, client_timezone_name())
        end = parse_client_datetime(data["end"], current_user, client_timezone_name())
        start, end = _apply_overnight(start, end)
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "Некорректные данные"}), 400
    if not duration_ok(start, end):
        return jsonify({"ok": False, "error": "Длительность не больше 24 часов"}), 400
    ev.start_datetime = start
    ev.end_datetime = end
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/event/new", methods=["GET", "POST"])
@login_required
def new_event():
    form = EventForm()
    if form.validate_on_submit():
        start, end = combine_user_meeting(
            form.date.data, form.start_time.data, form.end_time.data, current_user,
            client_timezone_name(),
        )
        if not duration_ok(start, end):
            flash("Длительность события не больше 24 часов.", "danger")
            return render_template("event_form.html", form=form, form_title="Новое личное дело")
        ev = Event(
            title=form.title.data,
            description=form.description.data,
            start_datetime=start,
            end_datetime=end,
            event_type="personal",
            created_by=current_user.id,
        )
        db.session.add(ev)
        db.session.commit()
        flash("Дело добавлено в календарь.", "success")
        return redirect(url_for("main.tasks"))
    return render_template("event_form.html", form=form, form_title="Новое личное дело")


@bp.route("/event/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit_event(event_id):
    ev = db.session.get(Event, event_id)
    if ev is None or ev.created_by != current_user.id or ev.event_type != "personal":
        abort(404)
    form = EventForm()
    if request.method == "GET":
        tz = effective_timezone(current_user, client_timezone_name())
        start_local = utc_to_local(ev.start_datetime, tz)
        end_local = utc_to_local(ev.end_datetime, tz)
        form.title.data = ev.title
        form.description.data = ev.description
        form.date.data = start_local.date()
        form.start_time.data = start_local.time()
        form.end_time.data = end_local.time()
    if form.validate_on_submit():
        start, end = combine_user_meeting(
            form.date.data, form.start_time.data, form.end_time.data, current_user,
            client_timezone_name(),
        )
        if not duration_ok(start, end):
            flash("Длительность события не больше 24 часов.", "danger")
            return render_template("event_form.html", form=form, form_title="Редактировать дело")
        ev.title = form.title.data
        ev.description = form.description.data
        ev.start_datetime = start
        ev.end_datetime = end
        db.session.commit()
        flash("Дело обновлено.", "success")
        return redirect(url_for("main.calendar"))
    return render_template("event_form.html", form=form, form_title="Редактировать дело")
