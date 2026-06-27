from sqlalchemy import text

from flask import jsonify, current_app

from app import db
from app.routes import bp


@bp.route("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"ok": True, "service": "meetplan", "db": "ok"})
    except Exception:
        payload = {"ok": False, "service": "meetplan", "db": "error"}
        if not current_app.config.get("TESTING") and current_app.config.get("DEBUG"):
            payload["detail"] = "database unavailable"
        return jsonify(payload), 503
