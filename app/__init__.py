import os

from flask import Flask, jsonify, request, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_migrate import Migrate
from sqlalchemy import inspect
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config, is_production_env

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = "main.login"
login_manager.login_message = "Пожалуйста, войдите, чтобы продолжить."
login_manager.login_message_category = "warning"


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    from app.time_utils import format_dt

    @app.template_filter("user_dt")
    def user_dt_filter(dt, fmt="%d.%m.%Y в %H:%M"):
        from flask_login import current_user
        from app.helpers import client_timezone_name
        if not dt:
            return ""
        user = current_user if current_user.is_authenticated else None
        return format_dt(dt, user, fmt, client_timezone_name())

    is_prod = is_production_env()

    if (
        not app.config.get("TESTING")
        and is_prod
        and app.config["SECRET_KEY"] == "dev-secret"
    ):
        raise RuntimeError("Set SECRET_KEY environment variable in production.")

    if (
        not app.config.get("TESTING")
        and is_prod
        and not os.environ.get("DATABASE_URL")
    ):
        raise RuntimeError("Set DATABASE_URL environment variable in production.")

    if is_prod:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    from app.routes import bp as main_bp

    app.register_blueprint(main_bp)

    def _wants_json():
        return (
            request.path.startswith("/api/")
            or request.accept_mimetypes.best == "application/json"
            or request.is_json
        )

    def _json_http_error(e):
        code = getattr(e, "code", 500) or 500
        desc = getattr(e, "description", None) or "Ошибка запроса"
        if _wants_json():
            return jsonify({"ok": False, "error": desc}), code
        if hasattr(e, "get_response"):
            return e.get_response()
        return desc, code

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def http_client_error(e):
        return _json_http_error(e)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if _wants_json():
            return jsonify({"ok": False, "error": "Сессия устарела. Обновите страницу."}), 400
        return render_template_string(
            "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Сессия устарела</title></head><body style='font-family:sans-serif;padding:2rem'>"
            "<h1>Сессия устарела</h1>"
            "<p>Обновите страницу и повторите действие.</p>"
            "<p><a href='/'>На главную</a></p>"
            "</body></html>"
        ), 400

    @app.errorhandler(429)
    def too_many_requests(e):
        if _wants_json():
            return jsonify({"ok": False, "error": "Слишком много попыток. Подождите немного."}), 429
        return render_template_string(
            "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Слишком много попыток</title></head><body style='font-family:sans-serif;padding:2rem'>"
            "<h1>Слишком много попыток</h1>"
            "<p>Подождите несколько минут и попробуйте снова.</p>"
            "<p><a href='{{ url_for(\"main.login\") }}'>Вернуться ко входу</a></p>"
            "</body></html>"
        ), 429

    with app.app_context():
        is_test = app.config.get("TESTING")
        has_tables = bool(inspect(db.engine).get_table_names())

        if is_test or not is_prod or not has_tables:
            db.create_all()
        ensure_schema()
        seed_statuses()
        seed_organizations()
        assign_default_organization()
        sync_bootstrap_admins()
        ensure_invite_tokens()

    return app


def ensure_schema():
    """Лёгкая авто-миграция: добавляет недостающие колонки в существующую БД."""
    from sqlalchemy import inspect, text

    def bool_default(value):
        if db.engine.dialect.name == "postgresql":
            return "TRUE" if value else "FALSE"
        return "1" if value else "0"

    inspector = inspect(db.engine)
    if "users" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "avatar" not in cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN avatar VARCHAR(256)"))
            db.session.commit()
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "avatar_data" not in cols:
            blob_type = "BYTEA" if db.engine.dialect.name == "postgresql" else "BLOB"
            db.session.execute(text(f"ALTER TABLE users ADD COLUMN avatar_data {blob_type}"))
            db.session.commit()
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "avatar_mimetype" not in cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN avatar_mimetype VARCHAR(64)"))
            db.session.commit()
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "organization_id" not in cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN organization_id INTEGER"))
            db.session.commit()
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "role" not in cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(16) DEFAULT 'member'"))
            db.session.commit()
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "timezone" not in cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN timezone VARCHAR(64) DEFAULT 'Europe/Moscow'"))
            db.session.commit()
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "invite_token" not in cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN invite_token VARCHAR(32)"))
            db.session.commit()
        _ensure_unique_index("users", "ix_users_invite_token", "(invite_token)")
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "hide_calendar_details_from_friends" not in cols:
            db.session.execute(text(
                "ALTER TABLE users ADD COLUMN hide_calendar_details_from_friends "
                f"BOOLEAN DEFAULT {bool_default(False)} NOT NULL"
            ))
            db.session.commit()
    if "friendships" not in inspector.get_table_names():
        from app.models import Friendship
        Friendship.__table__.create(db.engine)
    elif "friendships" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("friendships")]
        if "requester_shares_details" not in cols:
            db.session.execute(text(
                "ALTER TABLE friendships ADD COLUMN requester_shares_details "
                f"BOOLEAN DEFAULT {bool_default(True)} NOT NULL"
            ))
            db.session.commit()
        cols = [c["name"] for c in inspector.get_columns("friendships")]
        if "addressee_shares_details" not in cols:
            db.session.execute(text(
                "ALTER TABLE friendships ADD COLUMN addressee_shares_details "
                f"BOOLEAN DEFAULT {bool_default(True)} NOT NULL"
            ))
            db.session.commit()
        _ensure_friendship_unordered_unique()
    if "tasks" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("tasks")]
        if "due_time" not in cols:
            db.session.execute(text("ALTER TABLE tasks ADD COLUMN due_time TIME"))
            db.session.commit()
    if "meeting_requests" in inspector.get_table_names():
        _ensure_unique_index(
            "meeting_requests", "uq_meeting_requests_event_id", "(event_id)"
        )
    if "event_participants" in inspector.get_table_names():
        _ensure_unique_index(
            "event_participants", "uq_event_participant", "(event_id, user_id)"
        )
    migrate_legacy_avatars()


def _index_exists(table, name):
    from sqlalchemy import inspect

    return any(idx.get("name") == name for idx in inspect(db.engine).get_indexes(table))


def _ensure_unique_index(table, name, columns_sql):
    from sqlalchemy import text

    if _index_exists(table, name):
        return
    try:
        db.session.execute(text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table} {columns_sql}"
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _ensure_friendship_unordered_unique():
    from sqlalchemy import text

    if _index_exists("friendships", "uq_friendship_unordered"):
        return
    dialect = db.engine.dialect.name
    expr = (
        "(LEAST(requester_id, addressee_id), GREATEST(requester_id, addressee_id))"
        if dialect == "postgresql"
        else "(min(requester_id, addressee_id), max(requester_id, addressee_id))"
    )
    try:
        db.session.execute(text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_friendship_unordered ON friendships {expr}"
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


def migrate_legacy_avatars():
    """Переносит файлы аватаров с диска в БД (если ещё не перенесены)."""
    import os

    from flask import current_app

    from app.models import User

    users = (
        User.query
        .filter(User.avatar.isnot(None), User.avatar_data.is_(None))
        .all()
    )
    if not users:
        return

    changed = False
    for user in users:
        path = os.path.join(current_app.static_folder, user.avatar)
        if not os.path.isfile(path):
            user.avatar = None
            changed = True
            continue
        with open(path, "rb") as fh:
            user.avatar_data = fh.read()
        user.avatar_mimetype = _legacy_avatar_mimetype(user.avatar)
        user.avatar = None
        changed = True
    if changed:
        db.session.commit()


def _legacy_avatar_mimetype(relative_path):
    ext = relative_path.rsplit(".", 1)[-1].lower() if relative_path else ""
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(ext, "image/jpeg")


def seed_statuses():
    """Создаёт справочник статусов при первом запуске."""
    from app.models import Status

    defaults = [
        (1, "Ожидает", "#8b5cf6"),
        (2, "Подтверждено", "#3b82f6"),
        (3, "Отклонено", "#ef4444"),
        (4, "Отменено", "#6b7280"),
    ]
    for sid, name, color in defaults:
        if not db.session.get(Status, sid):
            db.session.add(Status(id=sid, name=name, color=color))
    db.session.commit()


def seed_organizations():
    from app.models import Organization

    if Organization.query.count() == 0:
        db.session.add(Organization(id=1, name="MeetPlan"))
        db.session.commit()


def ensure_invite_tokens():
    from app.models import User

    changed = False
    for user in User.query.filter(User.invite_token.is_(None)).all():
        user.ensure_invite_token()
        changed = True
    if changed:
        db.session.commit()


def assign_default_organization():
    from app.models import User

    users = User.query.filter(User.organization_id.is_(None)).all()
    if not users:
        return
    for user in users:
        user.organization_id = 1
        if user.role is None:
            user.role = "member"
    db.session.commit()


def sync_bootstrap_admins():
    from app.helpers import sync_bootstrap_admins as _sync

    _sync()


@login_manager.user_loader
def load_user(user_id):
    from app.models import User

    return db.session.get(User, int(user_id))
