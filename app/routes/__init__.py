from flask import Blueprint
from flask_login import current_user

bp = Blueprint("main", __name__)

from app.helpers import pending_count
from app.time_utils import user_timezone

from app.routes import auth, calendar, meetings, tasks, users, settings, stats, admin, health  # noqa: E402,F401


@bp.app_context_processor
def inject_globals():
    tz = user_timezone(current_user) if current_user.is_authenticated else None
    return {
        "pending_badge": pending_count(),
        "user_timezone": str(tz) if tz else "Europe/Moscow",
    }
