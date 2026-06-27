"""Общие хелперы приложения."""

import os
from functools import wraps
from time import time

from flask import current_app, request, abort
from flask_login import current_user

from app import db
from app.models import MeetingRequest, User
from app.utils import STATUS_PENDING

MAX_AVATAR_BYTES = 2 * 1024 * 1024

_login_attempts = {}
RATE_LIMIT_WINDOW = 300
RATE_LIMIT_MAX = 10


def pending_count():
    if not current_user.is_authenticated:
        return 0
    return MeetingRequest.query.filter_by(
        to_user_id=current_user.id, status_id=STATUS_PENDING
    ).count()


def guess_image_mimetype(filename, fallback="image/jpeg"):
    ext = filename.rsplit(".", 1)[-1].lower() if filename else ""
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(ext, fallback)


def remove_legacy_avatar_file(relative_path):
    if not relative_path:
        return
    path = os.path.join(current_app.static_folder, relative_path)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def colleagues_query():
    """Пользователи той же организации, кроме текущего."""
    q = User.query.filter(User.id != current_user.id)
    if current_user.organization_id:
        q = q.filter(User.organization_id == current_user.organization_id)
    return q.order_by(User.username)


def meeting_user_choices():
    return [(u.id, f"{u.username} ({u.email})") for u in colleagues_query().all()]


def rate_limit(scope="default"):
    """Простой in-memory rate limit по IP."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            from flask import current_app
            if current_app.config.get("TESTING"):
                return view(*args, **kwargs)
            ip = request.remote_addr or "unknown"
            key = f"{scope}:{ip}"
            now = time()
            attempts = [t for t in _login_attempts.get(key, []) if now - t < RATE_LIMIT_WINDOW]
            if len(attempts) >= RATE_LIMIT_MAX:
                abort(429)
            attempts.append(now)
            _login_attempts[key] = attempts
            return view(*args, **kwargs)

        return wrapped

    return decorator


def create_meeting_event(creator_id, to_user_id, title, description, start, end):
    """Создаёт встречу, запрос и участников."""
    from app.models import Event, MeetingRequest, EventParticipant

    ev = Event(
        title=title,
        description=description or "",
        start_datetime=start,
        end_datetime=end,
        event_type="meeting",
        created_by=creator_id,
    )
    db.session.add(ev)
    db.session.flush()

    req = MeetingRequest(
        event_id=ev.id,
        from_user_id=creator_id,
        to_user_id=to_user_id,
        status_id=STATUS_PENDING,
    )
    db.session.add(req)
    db.session.add(EventParticipant(event_id=ev.id, user_id=creator_id, status_id=2))
    db.session.add(EventParticipant(event_id=ev.id, user_id=to_user_id, status_id=STATUS_PENDING))
    return ev
