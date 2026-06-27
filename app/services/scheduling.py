"""Логика занятости, конфликтов и поиска свободного времени."""

from datetime import datetime, timedelta, time as dt_time, date

from app import db
from app.models import Event, EventParticipant, Task, MeetingRequest, User
from app.utils import STATUS_REJECTED, STATUS_CANCELLED

WORK_START = dt_time(7, 0)
WORK_END = dt_time(22, 0)
SLOT_MINUTES = 60


def _overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and a_end > b_start


def _active_meeting_status_ids():
    return [1, 2]  # pending, confirmed


def busy_blocks(user_id, range_start, range_end, exclude_event_id=None):
    """Интервалы занятости пользователя в заданном диапазоне."""
    blocks = []

    personal_q = Event.query.filter(
        Event.created_by == user_id,
        Event.event_type == "personal",
        Event.end_datetime > range_start,
        Event.start_datetime < range_end,
    )
    if exclude_event_id:
        personal_q = personal_q.filter(Event.id != exclude_event_id)
    for ev in personal_q.all():
        blocks.append({
            "user_id": user_id,
            "start": ev.start_datetime,
            "end": ev.end_datetime,
            "title": ev.title,
            "kind": "personal",
        })

    parts = (
        EventParticipant.query
        .join(Event, Event.id == EventParticipant.event_id)
        .join(MeetingRequest, MeetingRequest.event_id == Event.id)
        .filter(
            EventParticipant.user_id == user_id,
            Event.event_type == "meeting",
            MeetingRequest.status_id.in_(_active_meeting_status_ids()),
            Event.end_datetime > range_start,
            Event.start_datetime < range_end,
        )
    )
    if exclude_event_id:
        parts = parts.filter(Event.id != exclude_event_id)
    for p in parts.all():
        blocks.append({
            "user_id": user_id,
            "start": p.event.start_datetime,
            "end": p.event.end_datetime,
            "title": p.event.title,
            "kind": "meeting",
        })

    tasks = (
        Task.query
        .filter_by(user_id=user_id, done=False)
        .filter(Task.due_date.isnot(None))
        .all()
    )
    for task in tasks:
        start_t = task.due_time or dt_time(9, 0)
        start = datetime.combine(task.due_date, start_t)
        end = start + timedelta(hours=1)
        if _overlaps(start, end, range_start, range_end):
            blocks.append({
                "user_id": user_id,
                "start": start,
                "end": end,
                "title": task.title,
                "kind": "task",
            })

    return blocks


def find_conflicts(user_ids, start, end, exclude_event_id=None):
    """Конфликты расписания для списка пользователей."""
    conflicts = []
    for uid in user_ids:
        user = db.session.get(User, uid)
        if user is None:
            continue
        for block in busy_blocks(uid, start, end, exclude_event_id):
            if _overlaps(block["start"], block["end"], start, end):
                conflicts.append({
                    "user_id": uid,
                    "username": user.username,
                    "title": block["title"],
                    "kind": block["kind"],
                    "start": block["start"].isoformat(),
                    "end": block["end"].isoformat(),
                })
    return conflicts


def mutual_free_slots(user_a_id, user_b_id, days=7):
    """Свободные часовые слоты для двух пользователей на ближайшие days дней."""
    today = date.today()
    slots = []
    day = today
    end_day = today + timedelta(days=days)

    while day < end_day:
        slot_start = datetime.combine(day, WORK_START)
        day_end = datetime.combine(day, WORK_END)
        while slot_start + timedelta(minutes=SLOT_MINUTES) <= day_end:
            slot_end = slot_start + timedelta(minutes=SLOT_MINUTES)
            c1 = find_conflicts([user_a_id], slot_start, slot_end)
            c2 = find_conflicts([user_b_id], slot_start, slot_end)
            if not c1 and not c2:
                slots.append({
                    "date": day.isoformat(),
                    "start": slot_start.strftime("%H:%M"),
                    "end": slot_end.strftime("%H:%M"),
                    "label": slot_start.strftime("%d.%m.%Y %H:%M – ") + slot_end.strftime("%H:%M"),
                })
            slot_start = slot_end
        day += timedelta(days=1)

    return slots[:42]
