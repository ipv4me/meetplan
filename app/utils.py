"""Вспомогательные функции."""

from datetime import datetime

from sqlalchemy.orm import joinedload

from app import db
from app.models import Event, EventParticipant, Task, User
from app.friends_service import friend_shares_details_with
from app.time_utils import utc_iso, task_block_utc

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
    from app.helpers import client_timezone_name

    result = []
    is_self = viewer_id is None or viewer_id == user_id
    effective_viewer = user_id if viewer_id is None else viewer_id
    can_see_details = is_self or friend_shares_details_with(user_id, viewer_id)
    owner = db.session.get(User, user_id)
    client_tz = client_timezone_name()

    personal = Event.query.filter_by(created_by=user_id, event_type="personal").all()
    for ev in personal:
        if is_self or can_see_details:
            result.append(_to_fc(ev, STATUS_CONFIRMED, viewer_id=effective_viewer))
        else:
            result.append(_to_fc_busy(ev))

    parts = (
        EventParticipant.query
        .options(joinedload(EventParticipant.event).joinedload(Event.request))
        .join(Event, Event.id == EventParticipant.event_id)
        .filter(EventParticipant.user_id == user_id, Event.event_type == "meeting")
        .all()
    )
    for p in parts:
        req = p.event.request
        status_id = req.status_id if req else p.status_id
        if status_id in (STATUS_REJECTED, STATUS_CANCELLED) and not is_self:
            continue
        if is_self or can_see_details or _viewer_in_event(p.event_id, viewer_id):
            result.append(_to_fc(p.event, status_id, viewer_id=effective_viewer))
        else:
            result.append(_to_fc_busy(p.event))

    if owner:
        if is_self:
            result.extend(_tasks_to_fc(owner, client_tz_name=client_tz))
        elif can_see_details:
            result.extend(_tasks_to_fc(owner, for_viewer=True, client_tz_name=client_tz))
        else:
            result.extend(_tasks_to_fc_busy(owner, client_tz_name=client_tz))

    return result


def _viewer_in_event(event_id, viewer_id):
    if not viewer_id:
        return False
    return EventParticipant.query.filter_by(event_id=event_id, user_id=viewer_id).first() is not None


def _tasks_to_fc(user, for_viewer=False, client_tz_name=None):
    """Задачи с датой — блоки в календаре."""
    items = []
    tasks = (
        Task.query
        .filter_by(user_id=user.id, done=False)
        .filter(Task.due_date.isnot(None))
        .all()
    )
    for task in tasks:
        utc_start, utc_end = task_block_utc(task, user, client_tz_name)
        bg, border, text = STYLE_TASK
        items.append({
            "id": f"task-{task.id}",
            "title": task.title,
            "start": utc_iso(utc_start),
            "end": utc_iso(utc_end),
            "backgroundColor": bg,
            "borderColor": border,
            "textColor": text,
            "editable": False,
            "extendedProps": {
                "description": "",
                "type": "task",
                "taskId": task.id,
                "statusId": STATUS_CONFIRMED,
                "statusLabel": "Задача",
                "isOwner": not for_viewer,
                "canDelete": not for_viewer,
                "accent": border,
            },
        })
    return items


def _tasks_to_fc_busy(user, client_tz_name=None):
    """Задачи с датой для чужого календаря — только занятость."""
    items = []
    tasks = (
        Task.query
        .filter_by(user_id=user.id, done=False)
        .filter(Task.due_date.isnot(None))
        .all()
    )
    bg, border, text = STYLE_PERSONAL
    for task in tasks:
        utc_start, utc_end = task_block_utc(task, user, client_tz_name)
        items.append({
            "id": f"task-{task.id}",
            "title": "Занят",
            "start": utc_iso(utc_start),
            "end": utc_iso(utc_end),
            "backgroundColor": bg,
            "borderColor": border,
            "textColor": text,
            "editable": False,
            "extendedProps": {
                "description": "",
                "type": "busy",
                "statusId": STATUS_CONFIRMED,
                "statusLabel": "Занят",
                "isOwner": False,
                "accent": border,
            },
        })
    return items


def _to_fc(ev, status_id, viewer_id=None):
    bg, border, text = event_style(ev, status_id)
    is_owner = viewer_id is not None and ev.created_by == viewer_id
    is_participant = False
    if viewer_id and ev.event_type == "meeting" and ev.request:
        is_participant = viewer_id in (ev.request.from_user_id, ev.request.to_user_id)
    can_cancel = (
        ev.event_type == "meeting"
        and is_participant
        and status_id in (STATUS_PENDING, STATUS_CONFIRMED)
    )
    can_delete = is_owner and ev.event_type in ("meeting", "personal")
    status_text = status_label(status_id) if ev.event_type == "meeting" else "Личное событие"
    # флаги дублируем на верхнем уровне — FullCalendar кладёт их в extendedProps
    return {
        "id": ev.id,
        "title": ev.title,
        "start": utc_iso(ev.start_datetime),
        "end": utc_iso(ev.end_datetime),
        "backgroundColor": bg,
        "borderColor": border,
        "textColor": text,
        "type": ev.event_type,
        "statusId": status_id,
        "statusLabel": status_text,
        "isOwner": is_owner,
        "canCancel": can_cancel,
        "canDelete": can_delete,
        "description": ev.description or "",
        "accent": border,
        "extendedProps": {
            "description": ev.description or "",
            "type": ev.event_type,
            "statusId": status_id,
            "statusLabel": status_text,
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
        "editable": False,
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


def ru_plural(n, one, few, many):
    """Русское склонение: 1 друг, 2 друга, 5 друзей, 21 друг…"""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return few
    return many
