"""Вспомогательные функции."""

from datetime import datetime, time as dt_time, timedelta

from app import db
from app.models import Event, EventParticipant, MeetingRequest, Task, User
from app.time_utils import utc_iso, task_block_local_iso, user_timezone

# Насыщенные цвета (легенда, левая полоса события)
COLOR_PERSONAL = "#f59e0b"   # личные дела — жёлтый
COLOR_PENDING = "#8b5cf6"    # ожидают подтверждения — фиолетовый
COLOR_CONFIRMED = "#3b82f6"  # подтверждённые встречи — синий
COLOR_REJECTED = "#ef4444"   # отклонённые — красный
COLOR_CANCELLED = "#6b7280"  # отменённые — серый

# Пастельные стили событий как на макете: (фон, левая полоса/рамка, текст).
STYLE_PERSONAL = ("#fef3c7", COLOR_PERSONAL, "#92400e")
STYLE_PENDING = ("#ede9fe", COLOR_PENDING, "#5b21b6")
STYLE_CONFIRMED = ("#dbeafe", COLOR_CONFIRMED, "#1e40af")
STYLE_REJECTED = ("#fee2e2", COLOR_REJECTED, "#991b1b")
STYLE_CANCELLED = ("#f3f4f6", COLOR_CANCELLED, "#374151")
STYLE_TASK = ("#ecfdf5", "#22c55e", "#166534")

STATUS_PENDING = 1
STATUS_CONFIRMED = 2
STATUS_REJECTED = 3
STATUS_CANCELLED = 4


def event_style(event, status_id):
    """Возвращает (фон, рамка, текст) для события календаря."""
    if event.event_type == "personal":
        return STYLE_PERSONAL
    if status_id == STATUS_CONFIRMED:
        return STYLE_CONFIRMED
    if status_id == STATUS_CANCELLED:
        return STYLE_CANCELLED
    if status_id == STATUS_REJECTED:
        return STYLE_REJECTED
    return STYLE_PENDING


def status_label(status_id):
    return {
        1: "Ожидает подтверждения",
        2: "Подтверждено",
        3: "Отклонено",
        4: "Отменено",
    }.get(status_id, "")


def events_for_user(user_id, viewer_id=None):
    """Список событий пользователя в формате FullCalendar."""
    result = []
    is_self = viewer_id is None or viewer_id == user_id
    owner = db.session.get(User, user_id)

    personal = Event.query.filter_by(created_by=user_id, event_type="personal").all()
    for ev in personal:
        if is_self:
            result.append(_to_fc(ev, STATUS_CONFIRMED, is_owner=True))
        else:
            result.append(_to_fc_busy(ev))

    parts = (
        EventParticipant.query
        .join(Event, Event.id == EventParticipant.event_id)
        .filter(EventParticipant.user_id == user_id, Event.event_type == "meeting")
        .all()
    )
    for p in parts:
        req = p.event.request
        status_id = req.status_id if req else p.status_id
        if status_id in (STATUS_REJECTED, STATUS_CANCELLED) and not is_self:
            continue
        result.append(_to_fc(p.event, status_id, is_owner=(p.event.created_by == user_id)))

    if is_self and owner:
        result.extend(_tasks_to_fc(owner))

    return result


def _tasks_to_fc(user):
    """Задачи с датой — блоки в календаре (локальное wall-clock время, без UTC-сдвига)."""
    items = []
    tasks = (
        Task.query
        .filter_by(user_id=user.id, done=False)
        .filter(Task.due_date.isnot(None))
        .all()
    )
    for task in tasks:
        local_start, local_end = task_block_local_iso(task)
        bg, border, text = STYLE_TASK
        items.append({
            "id": f"task-{task.id}",
            "title": task.title,
            "start": local_start,
            "end": local_end,
            "backgroundColor": bg,
            "borderColor": border,
            "textColor": text,
            "extendedProps": {
                "description": "",
                "type": "task",
                "taskId": task.id,
                "statusId": STATUS_CONFIRMED,
                "statusLabel": "Задача",
                "isOwner": True,
                "canDelete": True,
                "accent": border,
            },
        })
    return items


def _to_fc(ev, status_id, is_owner=False):
    bg, border, text = event_style(ev, status_id)
    can_cancel = (
        ev.event_type == "meeting"
        and status_id not in (STATUS_REJECTED, STATUS_CANCELLED)
    )
    can_delete = ev.event_type == "meeting"
    return {
        "id": ev.id,
        "title": ev.title,
        "start": utc_iso(ev.start_datetime),
        "end": utc_iso(ev.end_datetime),
        "backgroundColor": bg,
        "borderColor": border,
        "textColor": text,
        "extendedProps": {
            "description": ev.description or "",
            "type": ev.event_type,
            "statusId": status_id,
            "statusLabel": status_label(status_id) if ev.event_type == "meeting" else "Личное событие",
            "isOwner": is_owner,
            "canCancel": can_cancel,
            "canDelete": can_delete,
            "accent": border,
        },
        "editable": ev.event_type == "personal" and is_owner,
    }


def _to_fc_busy(ev):
    """Личное событие для чужого календаря — только занятость, без деталей."""
    bg, border, text = STYLE_PERSONAL
    return {
        "id": ev.id,
        "title": "Занят",
        "start": utc_iso(ev.start_datetime),
        "end": utc_iso(ev.end_datetime),
        "backgroundColor": bg,
        "borderColor": border,
        "textColor": text,
        "extendedProps": {
            "description": "",
            "type": "busy",
            "statusId": STATUS_CONFIRMED,
            "statusLabel": "Занят",
            "isOwner": False,
            "accent": border,
        },
    }


def combine(date_value, time_value):
    """Объединяет date и time в datetime."""
    return datetime.combine(date_value, time_value)
