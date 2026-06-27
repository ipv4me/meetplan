from datetime import datetime

from flask import render_template, jsonify, abort, request, flash, redirect, url_for
from flask_login import login_required, current_user

from app import db
from app.models import User, Event, MeetingRequest, Task
from app.forms import EventForm, MeetingForm
from app.utils import events_for_user, combine, STATUS_PENDING
from app.helpers import pending_count, colleagues_query
from app.routes import bp


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
    meeting_form = MeetingForm()
    return render_template(
        "calendar.html",
        pending_count=pending_count(),
        users=others,
        latest_request=latest_request,
        tasks=my_tasks,
        meeting_form=meeting_form,
    )


@bp.route("/api/events")
@login_required
def api_events():
    return jsonify(events_for_user(current_user.id))


@bp.route("/api/users/<int:user_id>/events")
@login_required
def api_user_events(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    return jsonify(events_for_user(user.id, viewer_id=current_user.id))


@bp.route("/api/events", methods=["POST"])
@login_required
def api_create_event():
    data = request.get_json() or {}
    try:
        title = (data["title"] or "").strip()
        start = datetime.fromisoformat(data["start"])
        end = datetime.fromisoformat(data["end"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "Некорректные данные"}), 400
    if not title or end <= start:
        return jsonify({"ok": False, "error": "Проверьте поля"}), 400

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


@bp.route("/event/new", methods=["GET", "POST"])
@login_required
def new_event():
    form = EventForm()
    if form.validate_on_submit():
        ev = Event(
            title=form.title.data,
            description=form.description.data,
            start_datetime=combine(form.date.data, form.start_time.data),
            end_datetime=combine(form.date.data, form.end_time.data),
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
        form.title.data = ev.title
        form.description.data = ev.description
        form.date.data = ev.start_datetime.date()
        form.start_time.data = ev.start_datetime.time()
        form.end_time.data = ev.end_datetime.time()
    if form.validate_on_submit():
        ev.title = form.title.data
        ev.description = form.description.data
        ev.start_datetime = combine(form.date.data, form.start_time.data)
        ev.end_datetime = combine(form.date.data, form.end_time.data)
        db.session.commit()
        flash("Дело обновлено.", "success")
        return redirect(url_for("main.calendar"))
    return render_template("event_form.html", form=form, form_title="Редактировать дело")
