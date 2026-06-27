from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "main.login"
login_manager.login_message = "Пожалуйста, войдите, чтобы продолжить."
login_manager.login_message_category = "warning"


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    from app.routes import bp as main_bp

    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()
        ensure_schema()
        seed_statuses()
        seed_organizations()
        assign_default_organization()

    return app


def ensure_schema():
    """Лёгкая авто-миграция: добавляет недостающие колонки в существующую БД."""
    from sqlalchemy import inspect, text

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
    if "tasks" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("tasks")]
        if "due_time" not in cols:
            db.session.execute(text("ALTER TABLE tasks ADD COLUMN due_time TIME"))
            db.session.commit()
    migrate_legacy_avatars()


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


def assign_default_organization():
    from app.models import User

    users = User.query.filter(User.organization_id.is_(None)).all()
    if not users:
        return
    for user in users:
        user.organization_id = 1
        if user.role is None:
            user.role = "member"
    if users and User.query.filter_by(role="admin").count() == 0:
        users[0].role = "admin"
    db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    from app.models import User

    return db.session.get(User, int(user_id))
