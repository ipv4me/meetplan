"""Друзья: запросы, принятие, ссылка-приглашение."""

from sqlalchemy import or_, and_

from app import db
from app.models import Friendship, User

FRIEND_PENDING = "pending"
FRIEND_ACCEPTED = "accepted"
FRIEND_REJECTED = "rejected"

SUGGEST_MIN_LEN = 2
SUGGEST_LIMIT = 10


def friendship_row(user_a_id, user_b_id):
    """Существующая связь между парой (в любом направлении) или None."""
    if user_a_id == user_b_id:
        return None
    low, high = sorted((user_a_id, user_b_id))
    return Friendship.query.filter(
        or_(
            and_(Friendship.requester_id == low, Friendship.addressee_id == high),
            and_(Friendship.requester_id == high, Friendship.addressee_id == low),
        )
    ).first()


def friendship_status(viewer_id, other_id):
    row = friendship_row(viewer_id, other_id)
    if row is None:
        return None
    if row.status == FRIEND_ACCEPTED:
        return "friend"
    if row.status == FRIEND_PENDING:
        return "outgoing" if row.requester_id == viewer_id else "incoming"
    return None


def friend_shares_details_with(owner_id, viewer_id):
    """Может ли viewer видеть названия личных дел и задач пользователя owner."""
    if owner_id == viewer_id:
        return True
    row = friendship_row(owner_id, viewer_id)
    if row is None or row.status != FRIEND_ACCEPTED:
        return False
    owner = db.session.get(User, owner_id)
    if owner and owner.hide_calendar_details_from_friends:
        return False
    if row.requester_id == owner_id:
        return bool(row.requester_shares_details)
    return bool(row.addressee_shares_details)


def set_friend_shares_details(owner_id, friend_id, share):
    row = friendship_row(owner_id, friend_id)
    if row is None or row.status != FRIEND_ACCEPTED:
        return None, "Друг не найден"
    if row.requester_id == owner_id:
        row.requester_shares_details = bool(share)
    else:
        row.addressee_shares_details = bool(share)
    db.session.commit()
    return row, None


def share_details_map(user_id):
    """friend_id -> показываем ли мы этому другу названия своих дел."""
    rows = Friendship.query.filter(
        Friendship.status == FRIEND_ACCEPTED,
        or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
    ).all()
    result = {}
    for row in rows:
        fid = row.other_user_id(user_id)
        if row.requester_id == user_id:
            result[fid] = bool(row.requester_shares_details)
        else:
            result[fid] = bool(row.addressee_shares_details)
    return result


def hide_details_map(user_id):
    """friend_id -> скрываем ли названия дел от этого друга."""
    return {fid: not share for fid, share in share_details_map(user_id).items()}


def are_friends(user_a_id, user_b_id):
    if user_a_id == user_b_id:
        return True
    row = friendship_row(user_a_id, user_b_id)
    return row is not None and row.status == FRIEND_ACCEPTED


def accept_friendship(requester_id, addressee_id, source="search"):
    """Создать или принять дружбу (для ссылки-приглашения)."""
    if requester_id == addressee_id:
        return None, "Нельзя добавить себя"
    existing = friendship_row(requester_id, addressee_id)
    if existing:
        if existing.status == FRIEND_ACCEPTED:
            return existing, None
        if existing.status == FRIEND_PENDING:
            existing.status = FRIEND_ACCEPTED
            db.session.commit()
            return existing, None
        existing.status = FRIEND_ACCEPTED
        db.session.commit()
        return existing, None
    row = Friendship(
        requester_id=requester_id,
        addressee_id=addressee_id,
        status=FRIEND_ACCEPTED,
        source=source,
    )
    db.session.add(row)
    db.session.commit()
    return row, None


def create_friend_request(requester_id, addressee_id):
    if requester_id == addressee_id:
        return None, "Нельзя добавить себя"
    existing = friendship_row(requester_id, addressee_id)
    if existing:
        if existing.status == FRIEND_ACCEPTED:
            return None, "Уже в друзьях"
        if existing.status == FRIEND_PENDING:
            if existing.requester_id == requester_id:
                return None, "Запрос уже отправлен"
            return None, "Этот пользователь уже отправил вам запрос — примите его"
        existing.status = FRIEND_PENDING
        existing.requester_id = requester_id
        existing.addressee_id = addressee_id
        existing.source = "search"
        db.session.commit()
        return existing, None
    row = Friendship(
        requester_id=requester_id,
        addressee_id=addressee_id,
        status=FRIEND_PENDING,
        source="search",
    )
    db.session.add(row)
    db.session.commit()
    return row, None


def respond_friend_request(friendship_id, user_id, accept):
    row = db.session.get(Friendship, friendship_id)
    if row is None or row.addressee_id != user_id or row.status != FRIEND_PENDING:
        return None, "Запрос не найден"
    if accept:
        row.status = FRIEND_ACCEPTED
    else:
        row.status = FRIEND_REJECTED
    db.session.commit()
    return row, None


def cancel_friend_request(friendship_id, user_id):
    row = db.session.get(Friendship, friendship_id)
    if row is None or row.requester_id != user_id or row.status != FRIEND_PENDING:
        return None, "Запрос не найден"
    db.session.delete(row)
    db.session.commit()
    return row, None


def friend_user_ids(user_id):
    rows = Friendship.query.filter(
        Friendship.status == FRIEND_ACCEPTED,
        or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
    ).all()
    return {r.other_user_id(user_id) for r in rows}


def pending_incoming(user_id):
    return (
        Friendship.query
        .filter_by(addressee_id=user_id, status=FRIEND_PENDING)
        .order_by(Friendship.created_at.desc())
        .all()
    )


def pending_outgoing(user_id):
    return (
        Friendship.query
        .filter_by(requester_id=user_id, status=FRIEND_PENDING)
        .order_by(Friendship.created_at.desc())
        .all()
    )


def _name_prefix_filter(q):
    """Имя или любое слово в имени начинается с q (без учёта регистра)."""
    start = f"{q}%"
    word = f"% {q}%"
    return or_(User.username.ilike(start), User.username.ilike(word))


def suggest_users_for_friend(query, viewer_id, limit=SUGGEST_LIMIT):
    """Подсказки: префикс по имени/фамилии или email."""
    q = (query or "").strip()
    if len(q) < SUGGEST_MIN_LEN:
        return []

    if "@" in q:
        candidates = (
            User.query
            .filter(User.id != viewer_id, User.email.ilike(f"{q.lower()}%"))
            .order_by(User.username)
            .limit(limit * 2)
            .all()
        )
    else:
        candidates = (
            User.query
            .filter(User.id != viewer_id, _name_prefix_filter(q))
            .order_by(User.username)
            .limit(limit * 2)
            .all()
        )

    results = []
    for user in candidates:
        status = friendship_status(viewer_id, user.id)
        if status == "friend":
            continue
        item = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "status": status,
        }
        if status == "outgoing":
            item["status_label"] = "Запрос отправлен"
        elif status == "incoming":
            item["status_label"] = "Ждёт вашего ответа"
        results.append(item)
        if len(results) >= limit:
            break
    return results
