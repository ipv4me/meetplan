from datetime import datetime

from flask import render_template, jsonify, abort, request
from flask_login import login_required, current_user

from app import db
from app.models import Task
from app.helpers import pending_count
from app.routes import bp

TASK_PALETTE = ["#f59e0b", "#3b82f6", "#22c55e", "#8b5cf6"]


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
    return render_template("tasks.html", tasks=items, pending_count=pending_count())


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


@bp.route("/api/tasks/<int:task_id>", methods=["PUT"])
@login_required
def api_update_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None or task.user_id != current_user.id:
        abort(404)
    data = request.get_json() or {}
    title = (data.get("title") or task.title).strip()
    if not title:
        return jsonify({"ok": False, "error": "Введите название"}), 400
    task.title = title
    if "due_date" in data:
        if data["due_date"]:
            try:
                task.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"ok": False, "error": "Некорректная дата"}), 400
        else:
            task.due_date = None
            task.due_time = None
    if "due_time" in data:
        if data["due_time"]:
            try:
                task.due_time = datetime.strptime(data["due_time"], "%H:%M").time()
            except ValueError:
                return jsonify({"ok": False, "error": "Некорректное время"}), 400
        else:
            task.due_time = None
    if task.due_time and not task.due_date:
        return jsonify({"ok": False, "error": "Укажите дату для времени"}), 400
    db.session.commit()
    return jsonify({
        "ok": True,
        "id": task.id,
        "title": task.title,
        "due": task.due_display or "",
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
