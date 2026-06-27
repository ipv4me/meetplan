import pytest

from app import create_app, db
from app.models import User, MeetingRequest
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test"
    ADMIN_EMAILS = frozenset({"owner@test.com"})
    DEFAULT_USER_TIMEZONE = "UTC"


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


def test_bootstrap_admin_and_promote(client, app):
    _register(client, "owner", "owner@test.com")
    _register(client, "member", "member@test.com")
    with app.app_context():
        owner = User.query.filter_by(email="owner@test.com").first()
        member = User.query.filter_by(email="member@test.com").first()
        assert owner.is_admin
        assert not member.is_admin
        owner_id = owner.id
        member_id = member.id

    _login(client, "member@test.com")
    assert client.get("/admin/users").status_code == 403

    _login(client, "owner@test.com")
    assert client.get("/admin/users").status_code == 200
    r = client.post(
        f"/api/admin/users/{member_id}/role",
        json={"role": "admin"},
    )
    assert r.get_json()["ok"] is True
    with app.app_context():
        assert User.query.get(member_id).is_admin

    r = client.post(
        f"/api/admin/users/{owner_id}/role",
        json={"role": "member"},
    )
    assert r.status_code == 403


def test_org_isolation_for_calendar(client, app):
    _register(client, "alice", "alice@test.com")
    _register(client, "bob", "bob@test.com")
    with app.app_context():
        alice = User.query.filter_by(email="alice@test.com").first()
        bob = User.query.filter_by(email="bob@test.com").first()
        alice.organization_id = 1
        bob.organization_id = 2
        db.session.commit()
        bob_id = bob.id

    _login(client, "alice@test.com")
    assert client.get(f"/users/{bob_id}/calendar").status_code == 404
    assert client.get(f"/api/users/{bob_id}/events").status_code == 404


def test_pending_request_guard(client, app):
    _register(client, "u1", "u1@test.com")
    _register(client, "u2", "u2@test.com")
    with app.app_context():
        u2 = User.query.filter_by(email="u2@test.com").first()
        u1 = User.query.filter_by(email="u1@test.com").first()
        u1.organization_id = u2.organization_id = 1
        u1.timezone = u2.timezone = "UTC"
        db.session.commit()
        uid2 = u2.id

    _login(client, "u1@test.com")
    client.post("/meeting/new", data={
        "to_user": uid2,
        "date": "2026-07-01",
        "start_time": "10:00",
        "end_time": "11:00",
        "title": "Sync",
        "description": "",
    }, follow_redirects=True)

    _login(client, "u2@test.com")
    with app.app_context():
        req = MeetingRequest.query.first()
        rid = req.id
    client.post(f"/api/requests/{rid}/confirm")
    r = client.post(f"/api/requests/{rid}/reject")
    assert r.status_code == 409


def test_meeting_cancel_by_invitee(client, app):
    _register(client, "host", "host@test.com")
    _register(client, "guest", "guest@test.com")
    with app.app_context():
        host = User.query.filter_by(email="host@test.com").first()
        guest = User.query.filter_by(email="guest@test.com").first()
        host.organization_id = guest.organization_id = 1
        host.timezone = guest.timezone = "UTC"
        db.session.commit()
        gid = guest.id

    _login(client, "host@test.com")
    client.post("/meeting/new", data={
        "to_user": gid,
        "date": "2026-07-05",
        "start_time": "12:00",
        "end_time": "13:00",
        "title": "Review",
        "description": "",
    }, follow_redirects=True)

    _login(client, "guest@test.com")
    with app.app_context():
        req = MeetingRequest.query.first()
        client.post(f"/api/requests/{req.id}/confirm")
        event_id = req.event_id

    r = client.post(f"/api/meetings/{event_id}/cancel")
    assert r.get_json()["ok"] is True


def test_health(client):
    r = client.get("/health")
    data = r.get_json()
    assert data["ok"] is True
    assert data.get("db") == "ok"


def test_notifications_redirects_to_requests(client):
    _register(client, "u1", "u1@test.com")
    _login(client, "u1@test.com")
    r = client.get("/notifications")
    assert r.status_code == 302
    assert "tab=incoming" in r.location


def test_email_normalized(client, app):
    _register(client, "Owner", "Owner@TEST.com")
    with app.app_context():
        user = User.query.filter_by(email="owner@test.com").first()
        assert user is not None
        assert user.is_admin


def test_avatar_org_isolation(client, app):
    _register(client, "alice", "alice@test.com")
    _register(client, "bob", "bob@test.com")
    with app.app_context():
        bob = User.query.filter_by(email="bob@test.com").first()
        bob.organization_id = 2
        db.session.commit()
        bob_id = bob.id

    _login(client, "alice@test.com")
    assert client.get(f"/avatars/{bob_id}").status_code == 404


def test_calendar_events_utc_format(client, app):
    _register(client, "tzuser", "tz@test.com")
    _login(client, "tz@test.com")
    client.post("/api/events", json={
        "title": "Meet",
        "start": "2026-08-01T10:00:00",
        "end": "2026-08-01T11:00:00",
    })
    r = client.get("/api/events")
    events = r.get_json()
    assert events
    assert events[0]["start"].endswith("Z")


def test_task_update(client, app):
    _register(client, "tuser", "t@test.com")
    _login(client, "t@test.com")
    r = client.post("/api/tasks", json={"title": "Old", "due_date": "2026-07-03"})
    tid = r.get_json()["id"]
    r = client.put(f"/api/tasks/{tid}", json={
        "title": "New title",
        "due_date": "2026-07-04",
        "due_time": "09:30",
    })
    data = r.get_json()
    assert data["ok"] is True
    assert data["title"] == "New title"
    assert "09:30" in data["due"]
