from flask import redirect, url_for
from flask_login import login_required

from app.helpers import admin_required
from app.routes import bp


@bp.route("/stats")
@login_required
@admin_required
def stats():
    return redirect(url_for("main.admin_users"))
