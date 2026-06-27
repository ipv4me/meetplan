import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Конфигурация приложения."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-me"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(basedir, "meetplan.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # загрузка аватаров
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024  # 3 МБ
    AVATAR_DIR = os.path.join(basedir, "app", "static", "uploads", "avatars")
    ALLOWED_AVATAR_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
