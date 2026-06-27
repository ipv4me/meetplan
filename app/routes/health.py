from flask import jsonify

from app.routes import bp


@bp.route("/health")
def health():
    return jsonify({"ok": True, "service": "meetplan"})
