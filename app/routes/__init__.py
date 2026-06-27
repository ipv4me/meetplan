from flask import Blueprint

bp = Blueprint("main", __name__)

from app.helpers import pending_count

from app.routes import auth, calendar, meetings, tasks, users, settings, stats  # noqa: E402,F401


@bp.app_context_processor
def inject_globals():
    return {"pending_badge": pending_count()}
