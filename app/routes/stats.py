from datetime import datetime

from flask import render_template
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import Event, EventParticipant, MeetingRequest, User
from app.utils import STATUS_PENDING, STATUS_CONFIRMED, STATUS_REJECTED, STATUS_CANCELLED
from app.helpers import pending_count, USERS_PER_PAGE
from app.time_utils import format_month_year, user_timezone
from app.routes import bp


@bp.route("/stats")
@login_required
def stats():
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    my_participations = (
        EventParticipant.query
        .join(Event, Event.id == EventParticipant.event_id)
        .filter(
            EventParticipant.user_id == current_user.id,
            Event.event_type == "meeting",
            Event.start_datetime >= month_start,
        )
        .all()
    )
    my_counts = _count_by_status(my_participations)

    org_counts = None
    if current_user.is_admin and current_user.organization_id:
        org_user_ids = [
            u.id for u in User.query.filter_by(
                organization_id=current_user.organization_id
            ).all()
        ]
        org_requests = (
            MeetingRequest.query
            .join(Event, Event.id == MeetingRequest.event_id)
            .filter(
                MeetingRequest.from_user_id.in_(org_user_ids),
                Event.start_datetime >= month_start,
            )
            .all()
        )
        org_counts = {
            "pending": sum(1 for r in org_requests if r.status_id == STATUS_PENDING),
            "confirmed": sum(1 for r in org_requests if r.status_id == STATUS_CONFIRMED),
            "rejected": sum(1 for r in org_requests if r.status_id == STATUS_REJECTED),
            "cancelled": sum(1 for r in org_requests if r.status_id == STATUS_CANCELLED),
            "total": len(org_requests),
        }

    return render_template(
        "stats.html",
        my_counts=my_counts,
        org_counts=org_counts,
        month_label=format_month_year(month_start, user_timezone(current_user)),
        pending_count=pending_count(),
    )


def _count_by_status(participations):
    counts = {"pending": 0, "confirmed": 0, "rejected": 0, "cancelled": 0, "total": 0}
    for p in participations:
        req = p.event.request
        sid = req.status_id if req else p.status_id
        counts["total"] += 1
        if sid == STATUS_PENDING:
            counts["pending"] += 1
        elif sid == STATUS_CONFIRMED:
            counts["confirmed"] += 1
        elif sid == STATUS_REJECTED:
            counts["rejected"] += 1
        elif sid == STATUS_CANCELLED:
            counts["cancelled"] += 1
    return counts
