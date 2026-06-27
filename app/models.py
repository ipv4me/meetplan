from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Organization {self.name}>"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    avatar = db.Column(db.String(256))  # устар.: путь в static/ (миграция в avatar_data)
    avatar_data = db.Column(db.LargeBinary)
    avatar_mimetype = db.Column(db.String(64))
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"))
    role = db.Column(db.String(16), default="member", nullable=False)
    timezone = db.Column(db.String(64), default="Europe/Moscow", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship("Organization")

    # Все события, созданные пользователем
    events = db.relationship(
        "Event", backref="creator", lazy="dynamic",
        foreign_keys="Event.created_by",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def has_avatar(self):
        return bool(self.avatar_data)

    @property
    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.username}>"


class Status(db.Model):
    __tablename__ = "statuses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    color = db.Column(db.String(16), nullable=False)

    def __repr__(self):
        return f"<Status {self.name}>"


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text)
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    # 'personal' — личное дело, 'meeting' — встреча
    event_type = db.Column(db.String(16), nullable=False, default="personal")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    participants = db.relationship(
        "EventParticipant", backref="event", lazy="dynamic",
        cascade="all, delete-orphan",
    )
    request = db.relationship(
        "MeetingRequest", backref="event", uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Event {self.title}>"


class MeetingRequest(db.Model):
    __tablename__ = "meeting_requests"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status_id = db.Column(db.Integer, db.ForeignKey("statuses.id"), nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    from_user = db.relationship("User", foreign_keys=[from_user_id])
    to_user = db.relationship("User", foreign_keys=[to_user_id])
    status = db.relationship("Status")

    def __repr__(self):
        return f"<MeetingRequest {self.id} status={self.status_id}>"


class EventParticipant(db.Model):
    __tablename__ = "event_participants"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status_id = db.Column(db.Integer, db.ForeignKey("statuses.id"), nullable=False, default=1)

    user = db.relationship("User")
    status = db.relationship("Status")


class Task(db.Model):
    """Личная задача — чек-лист «Мои дела», с датой показывается в календаре."""

    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(140), nullable=False)
    due_date = db.Column(db.Date)  # необязательная дата
    due_time = db.Column(db.Time)  # необязательное время
    done = db.Column(db.Boolean, default=False, nullable=False)
    color = db.Column(db.String(16), default="#3b82f6")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def due_display(self):
        """Форматированная дата/время для отображения."""
        if not self.due_date:
            return None
        text = self.due_date.strftime("%d.%m.%Y")
        if self.due_time:
            text += ", " + self.due_time.strftime("%H:%M")
        return text

    def __repr__(self):
        return f"<Task {self.title} done={self.done}>"
