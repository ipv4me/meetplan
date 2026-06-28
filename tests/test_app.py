import pytest

from app import create_app, db
from app.models import User, MeetingRequest, Event
from app.friends_service import accept_friendship, create_friend_request
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
    with client.session_transaction() as sess:
        sess.clear()
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


def _make_friends(app, email_a, email_b):
    with app.app_context():
        a = User.query.filter_by(email=email_a).first()
        b = User.query.filter_by(email=email_b).first()
        accept_friendship(a.id, b.id, source="invite")


def test_register_and_login(client):
    r = _register(client, "alice", "alice@test.com")
    assert r.status_code == 200
    r = client.get("/calendar")
    assert r.status_code == 200


def test_register_auto_login(client):
    _register(client, "newbie", "newbie@test.com")
    r = client.get("/calendar")
    assert r.status_code == 200
    r = client.get("/login", follow_redirects=False)
    assert r.status_code == 302
    assert "calendar" in r.location


def test_meeting_flow(client, app):
    _register(client, "user1", "u1@test.com")
    _register(client, "user2", "u2@test.com")
    _make_friends(app, "u1@test.com", "u2@test.com")
    with app.app_context():
        uid2 = User.query.filter_by(email="u2@test.com").first().id

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
    _make_friends(app, "a@test.com", "b@test.com")
    with app.app_context():
        uid2 = User.query.filter_by(email="b@test.com").first().id

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
    assert client.get("/stats").status_code == 403

    _login(client, "owner@test.com")
    assert client.get("/admin/users").status_code == 200
    r = client.get("/stats")
    assert r.status_code == 302
    assert "admin/users" in r.location
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


def test_friends_isolation_for_calendar(client, app):
    _register(client, "alice", "alice@test.com")
    _register(client, "bob", "bob@test.com")
    with app.app_context():
        bob_id = User.query.filter_by(email="bob@test.com").first().id

    _login(client, "alice@test.com")
    assert client.get(f"/users/{bob_id}/calendar").status_code == 404
    assert client.get(f"/api/users/{bob_id}/events").status_code == 404


def test_invite_link_adds_friend(client, app):
    _register(client, "host", "host@test.com")
    _register(client, "guest", "guest@test.com")
    with app.app_context():
        host = User.query.filter_by(email="host@test.com").first()
        host.ensure_invite_token()
        db.session.commit()
        token = host.invite_token

    _login(client, "guest@test.com")
    r = client.get(f"/friends/join/{token}", follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        from app.friends_service import are_friends
        host = User.query.filter_by(email="host@test.com").first()
        guest = User.query.filter_by(email="guest@test.com").first()
        assert are_friends(host.id, guest.id)


def test_friend_suggest_prefix(client, app):
    _register(client, "alice", "alice@test.com")
    _register(client, "Sasha", "sasha@test.com")
    _register(client, "Saveliy", "sav@test.com")
    _login(client, "alice@test.com")
    r = client.get("/api/friends/suggest?q=Sa")
    data = r.get_json()
    assert data["ok"] is True
    names = {u["username"] for u in data["users"]}
    assert "Sasha" in names
    assert "Saveliy" in names


def test_friend_request_by_id(client, app):
    _register(client, "alice", "alice@test.com")
    _register(client, "bob", "bob@test.com")
    _login(client, "alice@test.com")
    with app.app_context():
        bob_id = User.query.filter_by(email="bob@test.com").first().id
    r = client.post("/api/friends/request", json={"user_id": bob_id})
    assert r.get_json()["ok"] is True


def test_friend_suggest_email(client, app):
    _register(client, "alice", "alice@test.com")
    _register(client, "charlie", "charlie@test.com")
    _login(client, "alice@test.com")
    r = client.get("/api/friends/suggest?q=charlie@")
    data = r.get_json()
    assert data["ok"] is True
    assert any(u["email"] == "charlie@test.com" for u in data["users"])


def test_friend_search_request(client, app):
    _register(client, "alice", "alice@test.com")
    _register(client, "bob", "bob@test.com")

    _login(client, "alice@test.com")
    with app.app_context():
        bob_id = User.query.filter_by(email="bob@test.com").first().id
    r = client.post("/api/friends/request", json={"user_id": bob_id})
    assert r.get_json()["ok"] is True

    _login(client, "bob@test.com")
    with app.app_context():
        from app.friends_service import pending_incoming
        bob = User.query.filter_by(email="bob@test.com").first()
        incoming = pending_incoming(bob.id)
        assert len(incoming) == 1
        rid = incoming[0].id

    r = client.post(f"/api/friends/requests/{rid}/accept")
    assert r.get_json()["ok"] is True
    with app.app_context():
        from app.friends_service import are_friends
        alice = User.query.filter_by(email="alice@test.com").first()
        bob = User.query.filter_by(email="bob@test.com").first()
        assert are_friends(alice.id, bob.id)


def test_friend_cancel_outgoing(client, app):
    _register(client, "alice", "alice@test.com")
    _register(client, "bob", "bob@test.com")
    _login(client, "alice@test.com")
    with app.app_context():
        bob_id = User.query.filter_by(email="bob@test.com").first().id
    client.post("/api/friends/request", json={"user_id": bob_id})
    with app.app_context():
        from app.friends_service import pending_outgoing
        alice = User.query.filter_by(email="alice@test.com").first()
        oid = pending_outgoing(alice.id)[0].id
    r = client.post(f"/api/friends/requests/{oid}/cancel")
    assert r.get_json()["ok"] is True
    with app.app_context():
        from app.models import Friendship
        assert Friendship.query.count() == 0


def test_conflict_masks_private_titles(client, app):
    from app.friends_service import accept_friendship
    _register(client, "alice", "a@test.com")
    _register(client, "bob", "b@test.com")
    with app.app_context():
        a = User.query.filter_by(email="a@test.com").first()
        b = User.query.filter_by(email="b@test.com").first()
        a.timezone = b.timezone = "UTC"
        db.session.commit()
        accept_friendship(a.id, b.id)
        aid, bid = a.id, b.id
    _login(client, "b@test.com")
    client.post("/api/events", json={
        "title": "SECRET THERAPY",
        "start": "2026-09-01T10:00:00Z",
        "end": "2026-09-01T11:00:00Z",
    })
    client.post(f"/api/friends/{aid}/share-details", json={"share": False})
    _login(client, "a@test.com")
    r = client.post("/api/meetings/check-conflicts", json={
        "to_user": bid,
        "start": "2026-09-01T10:30:00Z",
        "end": "2026-09-01T11:30:00Z",
    })
    assert r.get_json()["ok"] is True
    conflicts = r.get_json()["conflicts"]
    bob_conflicts = [c for c in conflicts if c["user_id"] == bid]
    assert bob_conflicts
    assert bob_conflicts[0]["title"] == "Занят"
    assert bob_conflicts[0]["kind"] == "busy"


def test_conflict_shows_private_titles_by_default(client, app):
    from app.friends_service import accept_friendship
    _register(client, "alice", "a@test.com")
    _register(client, "bob", "b@test.com")
    with app.app_context():
        a = User.query.filter_by(email="a@test.com").first()
        b = User.query.filter_by(email="b@test.com").first()
        a.timezone = b.timezone = "UTC"
        db.session.commit()
        accept_friendship(a.id, b.id)
        bid = b.id
    _login(client, "b@test.com")
    client.post("/api/events", json={
        "title": "SECRET THERAPY",
        "start": "2026-09-01T10:00:00Z",
        "end": "2026-09-01T11:00:00Z",
    })
    _login(client, "a@test.com")
    r = client.post("/api/meetings/check-conflicts", json={
        "to_user": bid,
        "start": "2026-09-01T10:30:00Z",
        "end": "2026-09-01T11:30:00Z",
    })
    bob_conflicts = [c for c in r.get_json()["conflicts"] if c["user_id"] == bid]
    assert bob_conflicts
    assert bob_conflicts[0]["title"] == "SECRET THERAPY"
    assert bob_conflicts[0]["kind"] == "personal"


def test_conflict_masks_when_hidden_globally(client, app):
    from app.friends_service import accept_friendship
    _register(client, "alice", "a@test.com")
    _register(client, "bob", "b@test.com")
    with app.app_context():
        a = User.query.filter_by(email="a@test.com").first()
        b = User.query.filter_by(email="b@test.com").first()
        a.timezone = b.timezone = "UTC"
        db.session.commit()
        accept_friendship(a.id, b.id)
        bid = b.id
    _login(client, "b@test.com")
    client.post("/api/events", json={
        "title": "SECRET THERAPY",
        "start": "2026-09-01T10:00:00Z",
        "end": "2026-09-01T11:00:00Z",
    })
    client.post("/api/friends/hide-calendar-details", json={"hide": True})
    _login(client, "a@test.com")
    r = client.post("/api/meetings/check-conflicts", json={
        "to_user": bid,
        "start": "2026-09-01T10:30:00Z",
        "end": "2026-09-01T11:30:00Z",
    })
    bob_conflicts = [c for c in r.get_json()["conflicts"] if c["user_id"] == bid]
    assert bob_conflicts
    assert bob_conflicts[0]["title"] == "Занят"
    assert bob_conflicts[0]["kind"] == "busy"


def test_friend_calendar_share_details(client, app):
    from app.friends_service import accept_friendship
    _register(client, "alice", "a@test.com")
    _register(client, "bob", "b@test.com")
    with app.app_context():
        a = User.query.filter_by(email="a@test.com").first()
        b = User.query.filter_by(email="b@test.com").first()
        accept_friendship(a.id, b.id)
        aid, bid = a.id, b.id
    _login(client, "b@test.com")
    client.post("/api/events", json={
        "title": "Dentist",
        "start": "2026-09-02T09:00:00Z",
        "end": "2026-09-02T10:00:00Z",
    })
    _login(client, "a@test.com")
    r = client.get(f"/api/users/{bid}/events")
    titles = [e["title"] for e in r.get_json()]
    assert "Dentist" in titles
    _login(client, "b@test.com")
    client.post(f"/api/friends/{aid}/share-details", json={"share": False})
    _login(client, "a@test.com")
    r = client.get(f"/api/users/{bid}/events")
    titles = [e["title"] for e in r.get_json()]
    assert "Dentist" not in titles
    assert "Занят" in titles


def test_meeting_new_without_friends(client):
    _register(client, "solo", "solo@test.com")
    r = client.get("/meeting/new")
    assert r.status_code == 200
    assert "Сначала добавьте друзей".encode() in r.data or "друзей" in r.data.decode().lower()


def test_pending_request_guard(client, app):
    _register(client, "u1", "u1@test.com")
    _register(client, "u2", "u2@test.com")
    _make_friends(app, "u1@test.com", "u2@test.com")
    with app.app_context():
        u2 = User.query.filter_by(email="u2@test.com").first()
        u1 = User.query.filter_by(email="u1@test.com").first()
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
    _make_friends(app, "host@test.com", "guest@test.com")
    with app.app_context():
        guest = User.query.filter_by(email="guest@test.com").first()
        guest.timezone = "UTC"
        host = User.query.filter_by(email="host@test.com").first()
        host.timezone = "UTC"
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


def test_avatar_friends_isolation(client, app):
    _register(client, "alice", "alice@test.com")
    _register(client, "bob", "bob@test.com")
    with app.app_context():
        bob_id = User.query.filter_by(email="bob@test.com").first().id

    _login(client, "alice@test.com")
    assert client.get(f"/avatars/{bob_id}").status_code == 404


def test_calendar_events_local_wall_clock(client, app):
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
    assert events[0]["start"] == "2026-08-01T10:00:00"
    assert not events[0]["start"].endswith("Z")


def test_meeting_calendar_local_time(client, app):
    _register(client, "host", "host2@test.com")
    _register(client, "guest", "guest2@test.com")
    _make_friends(app, "host2@test.com", "guest2@test.com")
    with app.app_context():
        gid = User.query.filter_by(email="guest2@test.com").first().id

    _login(client, "host2@test.com")
    client.post("/meeting/new", data={
        "to_user": gid,
        "date": "2026-06-28",
        "start_time": "20:00",
        "end_time": "21:00",
        "title": "Обсуждение проекта",
        "description": "",
    }, follow_redirects=True)

    r = client.get("/api/events")
    meetings = [e for e in r.get_json() if e.get("extendedProps", {}).get("type") == "meeting"]
    assert len(meetings) == 1
    assert meetings[0]["start"] == "2026-06-28T20:00:00"
    assert meetings[0]["end"] == "2026-06-28T21:00:00"


def test_task_calendar_matches_due_time(client, app):
    _register(client, "tasktz", "tasktz@test.com")
    _login(client, "tasktz@test.com")
    client.post("/api/tasks", json={
        "title": "Walk",
        "due_date": "2026-06-27",
        "due_time": "20:00",
    })
    r = client.get("/api/events")
    tasks = [e for e in r.get_json() if e.get("extendedProps", {}).get("type") == "task"]
    assert len(tasks) == 1
    assert tasks[0]["start"] == "2026-06-27T20:00:00"
    assert not tasks[0]["start"].endswith("Z")
    assert tasks[0]["end"] == "2026-06-27T21:00:00"


def test_meeting_delete(client, app):
    _register(client, "host", "host@test.com")
    _register(client, "guest", "guest@test.com")
    _make_friends(app, "host@test.com", "guest@test.com")
    with app.app_context():
        gid = User.query.filter_by(email="guest@test.com").first().id

    _login(client, "host@test.com")
    client.post("/meeting/new", data={
        "to_user": gid,
        "date": "2026-07-06",
        "start_time": "10:00",
        "end_time": "11:00",
        "title": "Standup",
        "description": "",
    }, follow_redirects=True)

    with app.app_context():
        event_id = MeetingRequest.query.first().event_id

    r = client.delete(f"/api/meetings/{event_id}")
    assert r.get_json()["ok"] is True
    with app.app_context():
        assert MeetingRequest.query.count() == 0
        assert Event.query.count() == 0


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


def test_login_redirects_to_next(client, app):
    _register(client, "host", "host@test.com")
    _register(client, "guest", "guest@test.com")
    with app.app_context():
        token = User.query.filter_by(email="host@test.com").first().invite_token
    client.post("/logout", follow_redirects=True)
    r = client.get(f"/friends/join/{token}", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location
    assert "next=" in r.location
    r = client.post("/login", data={
        "email": "guest@test.com",
        "password": "secret123",
        "next": f"/friends/join/{token}",
    }, follow_redirects=False)
    assert r.status_code == 302
    assert f"/friends/join/{token}" in r.location


def test_friend_request_invalid_user_id(client):
    _register(client, "solo", "solo@test.com")
    _login(client, "solo@test.com")
    r = client.post("/api/friends/request", json={"user_id": "not-a-number"})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_meeting_hidden_from_friend_when_privacy_on(client, app):
    from app.friends_service import accept_friendship
    _register(client, "alice", "a@test.com")
    _register(client, "bob", "b@test.com")
    _register(client, "charlie", "c@test.com")
    with app.app_context():
        a = User.query.filter_by(email="a@test.com").first()
        b = User.query.filter_by(email="b@test.com").first()
        c = User.query.filter_by(email="c@test.com").first()
        accept_friendship(a.id, b.id)
        accept_friendship(b.id, c.id)
        aid, bid, cid = a.id, b.id, c.id
    _login(client, "b@test.com")
    client.post(f"/api/friends/{aid}/share-details", json={"share": False})
    client.post("/meeting/new", data={
        "to_user": cid,
        "date": "2026-08-01",
        "start_time": "10:00",
        "end_time": "11:00",
        "title": "SECRET SYNC",
        "description": "",
    }, follow_redirects=True)
    with app.app_context():
        req = MeetingRequest.query.first()
        client.post(f"/api/requests/{req.id}/confirm")
    _login(client, "a@test.com")
    r = client.get(f"/api/users/{bid}/events")
    titles = [e["title"] for e in r.get_json()]
    assert "SECRET SYNC" not in titles
    assert "Занят" in titles


def test_register_redirects_to_next(client, app):
    _register(client, "host", "host@test.com")
    with app.app_context():
        token = User.query.filter_by(email="host@test.com").first().invite_token
    client.post("/logout", follow_redirects=True)
    r = client.post("/register", data={
        "username": "guest2",
        "email": "guest2@test.com",
        "password": "secret123",
        "password2": "secret123",
        "next": f"/friends/join/{token}",
    }, follow_redirects=False)
    assert r.status_code == 302
    assert f"/friends/join/{token}" in r.location


def test_safe_redirect_blocks_external(app):
    with app.test_request_context("/login?next=https://evil.example/phish"):
        from app.helpers import safe_redirect_target
        target = safe_redirect_target()
        assert "calendar" in target
        assert "evil" not in target


def test_task_hidden_in_friend_calendar(client, app):
    from app.friends_service import accept_friendship
    _register(client, "alice", "a@test.com")
    _register(client, "bob", "b@test.com")
    with app.app_context():
        a = User.query.filter_by(email="a@test.com").first()
        b = User.query.filter_by(email="b@test.com").first()
        accept_friendship(a.id, b.id)
        aid, bid = a.id, b.id
    _login(client, "b@test.com")
    client.post("/api/tasks", json={
        "title": "SECRET TASK",
        "due_date": "2026-08-10",
        "due_time": "14:00",
    })
    client.post(f"/api/friends/{aid}/share-details", json={"share": False})
    _login(client, "a@test.com")
    r = client.get(f"/api/users/{bid}/events")
    titles = [e["title"] for e in r.get_json()]
    assert "SECRET TASK" not in titles
    assert "Занят" in titles


def test_meeting_delete_confirmed_forbidden(client, app):
    _register(client, "host", "host@test.com")
    _register(client, "guest", "guest@test.com")
    _make_friends(app, "host@test.com", "guest@test.com")
    with app.app_context():
        gid = User.query.filter_by(email="guest@test.com").first().id
    _login(client, "host@test.com")
    client.post("/meeting/new", data={
        "to_user": gid,
        "date": "2026-07-10",
        "start_time": "10:00",
        "end_time": "11:00",
        "title": "Review",
        "description": "",
    }, follow_redirects=True)
    _login(client, "guest@test.com")
    with app.app_context():
        req = MeetingRequest.query.first()
        client.post(f"/api/requests/{req.id}/confirm")
        event_id = req.event_id
    r = client.delete(f"/api/meetings/{event_id}")
    assert r.status_code == 403
    _login(client, "host@test.com")
    r = client.delete(f"/api/meetings/{event_id}")
    assert r.status_code == 409

