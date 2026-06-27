"""Вспомогательные функции."""

from datetime import datetime

from app.models import Event, EventParticipant, MeetingRequest

# Насыщенные цвета (легенда, левая полоса события)
COLOR_PERSONAL = "#f59e0b"   # личные дела — жёлтый
COLOR_PENDING = "#8b5cf6"    # ожидают подтверждения — фиолетовый
COLOR_CONFIRMED = "#3b82f6"  # подтверждённые встречи — синий
COLOR_REJECTED = "#ef4444"   # отклонённые — красный

# Пастельные стили событий как на макете: (фон, левая полоса/рамка, текст).
# Светлый фон + тёмный текст читаются и в светлой, и в тёмной теме.
STYLE_PERSONAL = ("#fef3c7", COLOR_PERSONAL, "#92400e")
STYLE_PENDING = ("#ede9fe", COLOR_PENDING, "#5b21b6")
STYLE_CONFIRMED = ("#dbeafe", COLOR_CONFIRMED, "#1e40af")
STYLE_REJECTED = ("#fee2e2", COLOR_REJECTED, "#991b1b")

STATUS_PENDING = 1
STATUS_CONFIRMED = 2
STATUS_REJECTED = 3


def event_style(event, status_id):
    """Возвращает (фон, рамка, текст) для события календаря."""
    if event.event_type == "personal":
        return STYLE_PERSONAL
    if status_id == STATUS_CONFIRMED:
        return STYLE_CONFIRMED
    if status_id == STATUS_REJECTED:
        return STYLE_REJECTED
    return STYLE_PENDING


def status_label(status_id):
    return {1: "Ожидает подтверждения", 2: "Подтверждено", 3: "Отклонено"}.get(status_id, "")


def events_for_user(user_id):
    """Список событий пользователя в формате FullCalendar.

    Включает личные события пользователя и встречи, в которых он участвует.
    """
    result = []

    # Личные события, созданные пользователем
    personal = Event.query.filter_by(created_by=user_id, event_type="personal").all()
    for ev in personal:
        result.append(_to_fc(ev, STATUS_CONFIRMED, is_owner=True))

    # Встречи, где пользователь — участник.
    # Цвет/статус берём из запроса на встречу (общий для обоих участников),
    # а не из персонального статуса — иначе создатель видел бы свою встречу
    # подтверждённой ещё до ответа приглашённого.
    parts = (
        EventParticipant.query
        .join(Event, Event.id == EventParticipant.event_id)
        .filter(EventParticipant.user_id == user_id, Event.event_type == "meeting")
        .all()
    )
    for p in parts:
        req = p.event.request
        status_id = req.status_id if req else p.status_id
        result.append(_to_fc(p.event, status_id, is_owner=(p.event.created_by == user_id)))

    return result


def _to_fc(ev, status_id, is_owner=False):
    bg, border, text = event_style(ev, status_id)
    return {
        "id": ev.id,
        "title": ev.title,
        "start": ev.start_datetime.isoformat(),
        "end": ev.end_datetime.isoformat(),
        "backgroundColor": bg,
        "borderColor": border,
        "textColor": text,
        "extendedProps": {
            "description": ev.description or "",
            "type": ev.event_type,
            "statusId": status_id,
            "statusLabel": status_label(status_id) if ev.event_type == "meeting" else "Личное событие",
            "isOwner": is_owner,
            "accent": border,
        },
    }


def combine(date_value, time_value):
    """Объединяет date и time в datetime."""
    return datetime.combine(date_value, time_value)
