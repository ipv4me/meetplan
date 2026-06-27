"""Общие хелперы приложения."""

import os
from functools import wraps
from time import time

from flask import current_app, request, abort, url_for
from flask_login import current_user

from sqlalchemy import false

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


def safe_redirect_target(default_endpoint="main.calendar"):
    """Безопасный URL для редиректа после входа (только относительные пути)."""
    from urllib.parse import urlparse

    nxt = request.args.get("next") or request.form.get("next")
    if not nxt:
        return url_for(default_endpoint)
    parsed = urlparse(nxt)
    if parsed.scheme or parsed.netloc or not nxt.startswith("/"):
        return url_for(default_endpoint)
    return nxt


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


def bootstrap_admin_emails():
    return current_app.config.get("ADMIN_EMAILS") or frozenset()


def is_bootstrap_admin(user):
    return user.email.lower() in bootstrap_admin_emails()


def apply_bootstrap_admin_role(user):
    if is_bootstrap_admin(user):
        user.role = "admin"


def sync_bootstrap_admins():
    """Гарантирует admin для email из ADMIN_EMAILS."""
    emails = bootstrap_admin_emails()
    if not emails:
        return
    changed = False
    for user in User.query.all():
        if user.email.lower() in emails and user.role != "admin":
            user.role = "admin"
            changed = True
    if changed:
        db.session.commit()


def admin_count(organization_id=None):
    """Число администраторов (платформа или организация)."""
    q = User.query.filter_by(role="admin")
    if organization_id is not None:
        q = q.filter_by(organization_id=organization_id)
    return q.count()


def platform_admin_count():
    return User.query.filter_by(role="admin").count()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def get_friend(user_id):
    """Принятый друг или сам пользователь."""
    from app.friends_service import are_friends

    if user_id == current_user.id:
        return current_user
    user = db.session.get(User, user_id)
    if user is None:
        return None
    if not are_friends(current_user.id, user_id):
        return None
    return user


def friends_query():
    """Принятые друзья (кроме текущего пользователя)."""
    from app.friends_service import friend_user_ids

    ids = friend_user_ids(current_user.id)
    if not ids:
        return User.query.filter(false())
    return User.query.filter(User.id.in_(ids)).order_by(User.username)


def valid_friend_ids():
    from app.friends_service import friend_user_ids

    return friend_user_ids(current_user.id)


def ensure_friend(user_id):
    user = get_friend(user_id)
    if user is None:
        abort(404)
    return user


def meeting_user_choices():
    return [(u.id, u.display_name) for u in friends_query().all()]


# совместимость со старыми импортами
get_colleague = get_friend
colleagues_query = friends_query
valid_colleague_ids = valid_friend_ids
ensure_colleague = ensure_friend


def validate_avatar_image(data):
    """Проверяет, что bytes — реальное изображение (Pillow)."""
    from io import BytesIO

    from PIL import Image

    try:
        img = Image.open(BytesIO(data))
        img.verify()
        img = Image.open(BytesIO(data))
        fmt = (img.format or "").lower()
        if fmt not in ("jpeg", "png", "gif", "webp"):
            return False, "Неподдерживаемый формат изображения"
        mimetype = {
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }.get(fmt, "image/jpeg")
        return True, mimetype
    except Exception:
        return False, "Файл не является изображением"


def _rate_key(scope):
    return f"{scope}:{client_ip()}"


def client_ip():
    """IP клиента с учётом reverse proxy (Render)."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def can_view_user(user_id):
    """Себя или друга — для аватаров и т.п."""
    if not current_user.is_authenticated:
        return False
    if user_id == current_user.id:
        return True
    if current_user.is_admin:
        user = db.session.get(User, user_id)
        return user is not None
    return get_friend(user_id) is not None


def ensure_viewable_user(user_id):
    if not can_view_user(user_id):
        abort(404)


def check_rate_limit(scope="login"):
    """Блокирует IP при слишком многих неудачных попытках."""
    if current_app.config.get("TESTING"):
        return
    key = _rate_key(scope)
    now = time()
    attempts = [t for t in _login_attempts.get(key, []) if now - t < RATE_LIMIT_WINDOW]
    _login_attempts[key] = attempts
    if len(attempts) >= RATE_LIMIT_MAX:
        abort(429)


def record_failed_login(scope="login"):
    if current_app.config.get("TESTING"):
        return
    key = _rate_key(scope)
    now = time()
    attempts = [t for t in _login_attempts.get(key, []) if now - t < RATE_LIMIT_WINDOW]
    attempts.append(now)
    _login_attempts[key] = attempts


def rate_limit(scope="default"):
    """Проверка rate limit перед обработкой (без записи успешных запросов)."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            check_rate_limit(scope)
            return view(*args, **kwargs)

        return wrapped

    return decorator


USERS_PER_PAGE = 20
REQUESTS_PER_PAGE = 15


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
