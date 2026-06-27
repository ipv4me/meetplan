from sqlalchemy import text

from flask import jsonify

from app import db
from app.routes import bp


@bp.route("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"ok": True, "service": "meetplan", "db": "ok"})
    except Exception as exc:
        return jsonify({"ok": False, "service": "meetplan", "db": str(exc)}), 503
