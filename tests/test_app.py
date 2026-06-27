import pytest

from app import create_app, db
from app.models import User, MeetingRequest
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test"


@pytest.fixture
def app():
    application = create_app(TestConfig)
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _register(client, username, email, password="secret123"):
    return client.post("/register", data={
        "username": username,
        "email": email,
        "password": password,
        "password2": password,
    }, follow_redirects=True)


def _login(client, email, password="secret123"):
    return client.post("/login", data={
        "email": email,
        "password": password,
    }, follow_redirects=True)


def test_register_and_login(client):
    r = _register(client, "alice", "alice@test.com")
    assert r.status_code == 200
    r = _login(client, "alice@test.com")
    assert r.status_code == 200


def test_meeting_flow(client, app):
    _register(client, "user1", "u1@test.com")
    _register(client, "user2", "u2@test.com")
    with app.app_context():
        u2 = User.query.filter_by(email="u2@test.com").first()
        u1 = User.query.filter_by(email="u1@test.com").first()
        u1.organization_id = u2.organization_id = 1
        db.session.commit()
        uid2 = u2.id

    _login(client, "u1@test.com")
    r = client.post("/meeting/new", data={
        "to_user": uid2,
        "date": "2026-07-01",
        "start_time": "10:00",
        "end_time": "11:00",
        "title": "Sync",
        "description": "",
    }, follow_redirects=True)
    assert r.status_code == 200

    _login(client, "u2@test.com")
    with app.app_context():
        req = MeetingRequest.query.first()
        assert req is not None
        rid = req.id
    r = client.post(f"/api/requests/{rid}/confirm")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_conflict_detection(client, app):
    _register(client, "alex", "a@test.com")
    _register(client, "bob", "b@test.com")
    with app.app_context():
        u1 = User.query.filter_by(email="a@test.com").first()
        u2 = User.query.filter_by(email="b@test.com").first()
        assert u1 and u2
        u1.organization_id = u2.organization_id = 1
        db.session.commit()
        uid2 = u2.id

    _login(client, "a@test.com")
    client.post("/api/events", json={
        "title": "Busy",
        "start": "2026-07-02T14:00:00",
        "end": "2026-07-02T15:00:00",
    })
    r = client.post("/api/meetings/check-conflicts", json={
        "to_user": uid2,
        "start": "2026-07-02T14:30:00",
        "end": "2026-07-02T15:30:00",
    })
    data = r.get_json()
    assert data["ok"] is True
    assert len(data["conflicts"]) >= 1


def test_tasks_with_time(client, app):
    _register(client, "tuser", "t@test.com")
    _login(client, "t@test.com")
    r = client.post("/api/tasks", json={
        "title": "Call",
        "due_date": "2026-07-03",
        "due_time": "16:00",
    })
    assert r.get_json()["ok"] is True
    _login(client, "t@test.com")
    r = client.get("/api/events")
    events = r.get_json()
    assert any("Call" in e.get("title", "") for e in events)
