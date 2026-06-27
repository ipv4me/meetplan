"""Друзья: запросы, принятие, ссылка-приглашение."""

from sqlalchemy import or_, and_

from app import db
from app.models import Friendship, User

FRIEND_PENDING = "pending"
FRIEND_ACCEPTED = "accepted"
FRIEND_REJECTED = "rejected"


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


def find_user_for_friend_search(query):
    """Сначала по имени (поле username), если не нашли — по email."""
    q = (query or "").strip()
    if not q:
        return None, "Введите имя или email"

    by_name = User.query.filter(User.username.ilike(q)).all()
    if len(by_name) == 1:
        return by_name[0], None
    if len(by_name) > 1:
        return None, "Найдено несколько человек с таким именем — укажите email"

    if "@" in q:
        user = User.query.filter_by(email=q.lower()).first()
        if user:
            return user, None

    return None, "Пользователь не найден"
