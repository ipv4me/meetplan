"""Логика занятости, конфликтов и поиска свободного времени."""

from datetime import datetime, timedelta, time as dt_time

from app import db
from app.models import Event, EventParticipant, Task, MeetingRequest, User
from app.friends_service import friend_shares_details_with
from app.utils import STATUS_PENDING, STATUS_CONFIRMED
from app.time_utils import local_to_utc, effective_timezone, utc_to_local, utcnow, format_dt

WORK_START = dt_time(7, 0)
WORK_END = dt_time(22, 0)
SLOT_MINUTES = 60


def _overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and a_end > b_start


def _active_meeting_status_ids():
    return [STATUS_PENDING, STATUS_CONFIRMED]


def busy_blocks(user_id, range_start, range_end, exclude_event_id=None, client_tz_name=None):
    """Интервалы занятости пользователя в заданном диапазоне (UTC)."""
    blocks = []
    user = db.session.get(User, user_id)

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
            "event_id": p.event.id,
            "start": p.event.start_datetime,
            "end": p.event.end_datetime,
            "title": p.event.title,
            "kind": "meeting",
        })

    if user:
        from app.time_utils import task_block_utc
        tasks = (
            Task.query
            .filter_by(user_id=user_id, done=False)
            .filter(Task.due_date.isnot(None))
            .all()
        )
        for task in tasks:
            start, end = task_block_utc(task, user, client_tz_name)
            if _overlaps(start, end, range_start, range_end):
                blocks.append({
                    "user_id": user_id,
                    "start": start,
                    "end": end,
                    "title": task.title,
                    "kind": "task",
                })

    return blocks


def find_conflicts(user_ids, start, end, exclude_event_id=None, viewer_id=None, client_tz_name=None):
    """Конфликты расписания для списка пользователей."""
    from app.utils import _viewer_in_event

    conflicts = []
    for uid in user_ids:
        user = db.session.get(User, uid)
        if user is None:
            continue
        for block in busy_blocks(uid, start, end, exclude_event_id, client_tz_name=client_tz_name):
            if _overlaps(block["start"], block["end"], start, end):
                title = block["title"]
                kind = block["kind"]
                if viewer_id is not None and uid != viewer_id:
                    if kind in ("personal", "task"):
                        if not friend_shares_details_with(uid, viewer_id):
                            title = "Занят"
                            kind = "busy"
                    elif kind == "meeting":
                        event_id = block.get("event_id")
                        if (
                            not friend_shares_details_with(uid, viewer_id)
                            and not (event_id and _viewer_in_event(event_id, viewer_id))
                        ):
                            title = "Занят"
                            kind = "busy"
                conflicts.append({
                    "user_id": uid,
                    "username": user.username,
                    "title": title,
                    "kind": kind,
                    "start": block["start"].isoformat(),
                    "end": block["end"].isoformat(),
                })
    return conflicts


def mutual_free_slots(user_a_id, user_b_id, days=7, viewer=None, client_tz_name=None):
    """Свободные слоты для двух пользователей (границы дня — в TZ устройства/viewer)."""
    tz = effective_timezone(viewer, client_tz_name)
    now_utc = utcnow()
    today = utc_to_local(now_utc, tz).date()
    range_start = local_to_utc(datetime.combine(today, WORK_START), tz)
    range_end = local_to_utc(datetime.combine(today + timedelta(days=days), WORK_END), tz)

    blocks_a = busy_blocks(user_a_id, range_start, range_end, client_tz_name=client_tz_name)
    blocks_b = busy_blocks(user_b_id, range_start, range_end, client_tz_name=client_tz_name)

    slots = []
    day = today
    end_day = today + timedelta(days=days)

    while day < end_day:
        slot_start_local = datetime.combine(day, WORK_START)
        day_end_local = datetime.combine(day, WORK_END)
        while slot_start_local + timedelta(minutes=SLOT_MINUTES) <= day_end_local:
            slot_end_local = slot_start_local + timedelta(minutes=SLOT_MINUTES)
            slot_start = local_to_utc(slot_start_local, tz)
            slot_end = local_to_utc(slot_end_local, tz)
            busy_a = any(_overlaps(b["start"], b["end"], slot_start, slot_end) for b in blocks_a)
            busy_b = any(_overlaps(b["start"], b["end"], slot_start, slot_end) for b in blocks_b)
            if not busy_a and not busy_b:
                slots.append({
                    "date": day.isoformat(),
                    "start": slot_start_local.strftime("%H:%M"),
                    "end": slot_end_local.strftime("%H:%M"),
                    "label": format_dt(slot_start, viewer, "%d.%m.%Y %H:%M", client_tz_name)
                    + " – "
                    + format_dt(slot_end, viewer, "%H:%M", client_tz_name),
                })
            slot_start_local = slot_end_local
        day += timedelta(days=1)

    return slots[:42]
