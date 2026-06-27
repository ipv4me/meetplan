import os
from datetime import datetime

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort,
    current_app,
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import User, Event, MeetingRequest, EventParticipant, Status, Task
from app.forms import (
    RegistrationForm, LoginForm, EventForm, MeetingForm, ChangePasswordForm, AvatarForm,
)
from app.utils import (
    events_for_user, combine, status_label,
    STATUS_PENDING, STATUS_CONFIRMED, STATUS_REJECTED,
)

bp = Blueprint("main", __name__)


# ----------------------------- Аутентификация ----------------------------- #

@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.calendar"))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Регистрация прошла успешно. Теперь войдите.", "success")
        return redirect(url_for("main.login"))
    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.calendar"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            flash("Неверный email или пароль.", "danger")
            return redirect(url_for("main.login"))
        login_user(user, remember=form.remember.data)
        return redirect(url_for("main.calendar"))
    return render_template("login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


# -------------------------------- Календарь -------------------------------- #

@bp.route("/")
@bp.route("/calendar")
@login_required
def calendar():
    # данные для виджетов дашборда (десктоп)
    others = User.query.filter(User.id != current_user.id).order_by(User.username).all()
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
    meeting_form = MeetingForm()  # для CSRF-токена виджета «Создание встречи»
    return render_template(
        "calendar.html",
        pending_count=_pending_count(),
        users=others,
        latest_request=latest_request,
        tasks=my_tasks,
        meeting_form=meeting_form,
    )


@bp.route("/api/events")
@login_required
def api_events():
    """Feed событий для FullCalendar."""
    return jsonify(events_for_user(current_user.id))


@bp.route("/api/users/<int:user_id>/events")
@login_required
def api_user_events(user_id):
    """Feed событий выбранного пользователя для просмотра занятости."""
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    return jsonify(events_for_user(user.id, viewer_id=current_user.id))


@bp.route("/api/events", methods=["POST"])
@login_required
def api_create_event():
    """Быстрое создание личного дела (AJAX из календаря)."""
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
    if ev is None or ev.created_by != current_user.id:
        abort(404)
    db.session.delete(ev)
    db.session.commit()
    return jsonify({"ok": True})


# --------------------------- Создание дел/встреч --------------------------- #

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
    form = EventForm(obj=ev)
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
        return redirect(url_for("main.tasks"))
    return render_template("event_form.html", form=form, form_title="Редактировать дело")


@bp.route("/meeting/new", methods=["GET", "POST"])
@login_required
def new_meeting():
    form = MeetingForm()
    # список пользователей кроме себя
    form.to_user.choices = [
        (u.id, f"{u.username} ({u.email})")
        for u in User.query.filter(User.id != current_user.id).order_by(User.username).all()
    ]
    if form.validate_on_submit():
        ev = Event(
            title=form.title.data,
            description=form.description.data,
            start_datetime=combine(form.date.data, form.start_time.data),
            end_datetime=combine(form.date.data, form.end_time.data),
            event_type="meeting",
            created_by=current_user.id,
        )
        db.session.add(ev)
        db.session.flush()  # получаем ev.id

        # запрос на встречу
        req = MeetingRequest(
            event_id=ev.id,
            from_user_id=current_user.id,
            to_user_id=form.to_user.data,
            status_id=STATUS_PENDING,
        )
        db.session.add(req)
        # участники: создатель — подтверждён, приглашённый — ожидает
        db.session.add(EventParticipant(event_id=ev.id, user_id=current_user.id, status_id=STATUS_CONFIRMED))
        db.session.add(EventParticipant(event_id=ev.id, user_id=form.to_user.data, status_id=STATUS_PENDING))
        db.session.commit()
        flash("Запрос на встречу отправлен.", "success")
        return redirect(url_for("main.requests_page"))

    # предзаполнение получателя (?to=<user_id>) при переходе со страницы участников
    preselect = request.args.get("to", type=int)
    if request.method == "GET" and preselect:
        form.to_user.data = preselect
    return render_template("meeting_form.html", form=form, form_title="Создать встречу")


@bp.route("/meeting/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit_meeting(event_id):
    ev = db.session.get(Event, event_id)
    if ev is None or ev.created_by != current_user.id or ev.event_type != "meeting":
        abort(404)
    form = MeetingForm()
    form.to_user.choices = [
        (u.id, f"{u.username} ({u.email})")
        for u in User.query.filter(User.id != current_user.id).order_by(User.username).all()
    ]
    if request.method == "GET":
        form.to_user.data = ev.request.to_user_id if ev.request else None
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
        # правка встречи => заново требуется подтверждение
        if ev.request:
            ev.request.to_user_id = form.to_user.data
            ev.request.status_id = STATUS_PENDING
        # пересобираем участников
        EventParticipant.query.filter_by(event_id=ev.id).delete()
        db.session.add(EventParticipant(event_id=ev.id, user_id=current_user.id, status_id=STATUS_CONFIRMED))
        db.session.add(EventParticipant(event_id=ev.id, user_id=form.to_user.data, status_id=STATUS_PENDING))
        db.session.commit()
        flash("Встреча обновлена, запрос отправлен повторно.", "success")
        return redirect(url_for("main.calendar"))
    return render_template("meeting_form.html", form=form, form_title="Редактировать встречу")


# --------------------------------- Запросы --------------------------------- #

@bp.route("/requests")
@login_required
def requests_page():
    incoming = (
        MeetingRequest.query
        .filter_by(to_user_id=current_user.id)
        .order_by(MeetingRequest.created_at.desc())
        .all()
    )
    outgoing = (
        MeetingRequest.query
        .filter_by(from_user_id=current_user.id)
        .order_by(MeetingRequest.created_at.desc())
        .all()
    )
    return render_template(
        "requests.html",
        incoming=incoming,
        outgoing=outgoing,
        pending_count=_pending_count(),
    )


@bp.route("/api/requests/<int:req_id>/<action>", methods=["POST"])
@login_required
def api_request_action(req_id, action):
    """Подтверждение/отклонение встречи приглашённым (AJAX)."""
    req = db.session.get(MeetingRequest, req_id)
    if req is None or req.to_user_id != current_user.id:
        abort(404)
    if action == "confirm":
        new_status = STATUS_CONFIRMED
    elif action == "reject":
        new_status = STATUS_REJECTED
    else:
        abort(400)

    req.status_id = new_status
    # обновляем статус участника-приглашённого
    part = EventParticipant.query.filter_by(
        event_id=req.event_id, user_id=current_user.id
    ).first()
    if part:
        part.status_id = new_status
    db.session.commit()
    return jsonify({"ok": True, "status": new_status, "label": status_label(new_status)})


# --------------------------------- Мои дела -------------------------------- #

TASK_PALETTE = ["#f59e0b", "#3b82f6", "#22c55e", "#8b5cf6"]  # как точки на макете


@bp.route("/tasks")
@login_required
def tasks():
    items = (
        Task.query
        .filter_by(user_id=current_user.id)
        .order_by(
            Task.done,
            Task.due_date.is_(None),
            Task.due_date,
            Task.due_time.is_(None),
            Task.due_time,
            Task.created_at.desc(),
        )
        .all()
    )
    return render_template("tasks.html", tasks=items, pending_count=_pending_count())


@bp.route("/api/tasks", methods=["POST"])
@login_required
def api_create_task():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "Введите название"}), 400

    due = None
    if data.get("due_date"):
        try:
            due = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"ok": False, "error": "Некорректная дата"}), 400

    due_time = None
    if data.get("due_time"):
        try:
            due_time = datetime.strptime(data["due_time"], "%H:%M").time()
        except ValueError:
            return jsonify({"ok": False, "error": "Некорректное время"}), 400
    if due_time and not due:
        return jsonify({"ok": False, "error": "Укажите дату для времени"}), 400

    count = Task.query.filter_by(user_id=current_user.id).count()
    task = Task(
        user_id=current_user.id,
        title=title,
        due_date=due,
        due_time=due_time,
        color=TASK_PALETTE[count % len(TASK_PALETTE)],
    )
    db.session.add(task)
    db.session.commit()
    return jsonify({
        "ok": True,
        "id": task.id,
        "title": task.title,
        "color": task.color,
        "due": task.due_display or "",
        "done": task.done,
    })


@bp.route("/api/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def api_toggle_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None or task.user_id != current_user.id:
        abort(404)
    task.done = not task.done
    db.session.commit()
    return jsonify({"ok": True, "done": task.done})


@bp.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def api_delete_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None or task.user_id != current_user.id:
        abort(404)
    db.session.delete(task)
    db.session.commit()
    return jsonify({"ok": True})


# -------------------------------- Профиль ---------------------------------- #

@bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html", pending_count=_pending_count())


# -------------------------------- Участники -------------------------------- #

@bp.route("/users")
@login_required
def users():
    others = User.query.filter(User.id != current_user.id).order_by(User.username).all()
    return render_template("users.html", users=others, pending_count=_pending_count())


@bp.route("/users/<int:user_id>/calendar")
@login_required
def user_calendar(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    return render_template(
        "user_calendar.html",
        viewed_user=user,
        pending_count=_pending_count(),
    )


# -------------------------------- Настройки -------------------------------- #

@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.old_password.data):
            flash("Текущий пароль неверен.", "danger")
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("Пароль изменён.", "success")
            return redirect(url_for("main.settings"))
    return render_template(
        "settings.html", form=form, avatar_form=AvatarForm(), pending_count=_pending_count()
    )


@bp.route("/avatar", methods=["POST"])
@login_required
def upload_avatar():
    form = AvatarForm()
    if form.validate_on_submit():
        file = form.avatar.data
        ext = file.filename.rsplit(".", 1)[-1].lower()
        os.makedirs(current_app.config["AVATAR_DIR"], exist_ok=True)
        filename = secure_filename(f"user_{current_user.id}.{ext}")
        file.save(os.path.join(current_app.config["AVATAR_DIR"], filename))
        # путь относительно static/ (с прямыми слэшами для url_for)
        current_user.avatar = f"uploads/avatars/{filename}"
        db.session.commit()
        flash("Аватар обновлён.", "success")
    else:
        for errors in form.errors.values():
            for e in errors:
                flash(e, "danger")
    return redirect(url_for("main.settings"))


@bp.route("/avatar/delete", methods=["POST"])
@login_required
def delete_avatar():
    if current_user.avatar:
        path = os.path.join(current_app.static_folder, current_user.avatar)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        current_user.avatar = None
        db.session.commit()
        flash("Аватар удалён.", "info")
    return redirect(url_for("main.settings"))


# ------------------------------ Уведомления -------------------------------- #

@bp.route("/notifications")
@login_required
def notifications():
    incoming = (
        MeetingRequest.query
        .filter_by(to_user_id=current_user.id)
        .order_by(MeetingRequest.created_at.desc())
        .all()
    )
    return render_template("notifications.html", incoming=incoming, pending_count=_pending_count())


@bp.route("/api/notifications")
@login_required
def api_notifications():
    """Polling для веб-уведомлений: входящие запросы, ожидающие ответа."""
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
            "when": r.event.start_datetime.strftime("%d.%m.%Y в %H:%M"),
        }
        for r in pending
    ]
    return jsonify({"count": len(items), "items": items})


# ------------------------------- Хелперы ----------------------------------- #

def _pending_count():
    """Кол-во входящих запросов, ожидающих ответа (для бейджа)."""
    if not current_user.is_authenticated:
        return 0
    return MeetingRequest.query.filter_by(
        to_user_id=current_user.id, status_id=STATUS_PENDING
    ).count()


@bp.app_context_processor
def inject_globals():
    """Доступно во всех шаблонах."""
    return {"pending_badge": _pending_count()}
