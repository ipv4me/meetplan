import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _parse_admin_emails(raw):
    return frozenset(
        e.strip().lower() for e in (raw or "").split(",") if e.strip()
    )


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret"

    # Email владельца (и доп. админов): всегда admin, нельзя снять через UI.
    # Пример: ADMIN_EMAILS=you@gmail.com
    ADMIN_EMAILS = _parse_admin_emails(os.environ.get("ADMIN_EMAILS"))

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///meetplan.db"

    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )

    AVATAR_DIR = os.path.join(BASE_DIR, "app", "static", "uploads", "avatars")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    SESSION_COOKIE_HTTPONLY = True
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024
    DEFAULT_USER_TIMEZONE = os.environ.get("DEFAULT_USER_TIMEZONE", "Europe/Moscow")
