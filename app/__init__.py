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


def seed_statuses():
    """Создаёт справочник статусов при первом запуске."""
    from app.models import Status

    defaults = [
        (1, "Ожидает", "#8b5cf6"),       # фиолетовый
        (2, "Подтверждено", "#3b82f6"),  # синий
        (3, "Отклонено", "#ef4444"),     # красный
    ]
    if Status.query.count() == 0:
        for sid, name, color in defaults:
            db.session.add(Status(id=sid, name=name, color=color))
        db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    from app.models import User

    return db.session.get(User, int(user_id))
