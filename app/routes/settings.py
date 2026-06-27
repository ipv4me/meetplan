from flask import render_template, redirect, url_for, flash, Response, request, abort
from flask_login import login_required, current_user

from app import db
from app.models import User
from app.forms import ChangePasswordForm, AvatarForm, TimezoneForm
from app.helpers import (
    pending_count, MAX_AVATAR_BYTES, guess_image_mimetype,
    remove_legacy_avatar_file, validate_avatar_image,
)
from app.time_utils import TIMEZONE_CHOICES
from app.routes import bp


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    form = ChangePasswordForm()
    tz_form = TimezoneForm()
    tz_form.timezone.choices = TIMEZONE_CHOICES

    if request.method == "POST":
        if request.form.get("form_name") == "timezone":
            if tz_form.validate_on_submit():
                current_user.timezone = tz_form.timezone.data
                db.session.commit()
                flash("Часовой пояс сохранён.", "success")
                return redirect(url_for("main.settings"))
        elif form.validate_on_submit():
            if not current_user.check_password(form.old_password.data):
                flash("Текущий пароль неверен.", "danger")
            else:
                current_user.set_password(form.new_password.data)
                db.session.commit()
                flash("Пароль изменён.", "success")
                return redirect(url_for("main.settings"))

    tz_form.timezone.data = current_user.timezone
    return render_template(
        "settings.html",
        form=form,
        tz_form=tz_form,
        avatar_form=AvatarForm(),
        pending_count=pending_count(),
    )


@bp.route("/avatar", methods=["POST"])
@login_required
def upload_avatar():
    form = AvatarForm()
    if form.validate_on_submit():
        file = form.avatar.data
        data = file.read()
        if len(data) > MAX_AVATAR_BYTES:
            flash("Файл слишком большой (максимум 2 МБ).", "danger")
            return redirect(url_for("main.settings"))
        ok, mimetype_or_err = validate_avatar_image(data)
        if not ok:
            flash(mimetype_or_err, "danger")
            return redirect(url_for("main.settings"))
        remove_legacy_avatar_file(current_user.avatar)
        current_user.avatar_data = data
        current_user.avatar_mimetype = mimetype_or_err
        current_user.avatar = None
        db.session.commit()
        flash("Аватар обновлён.", "success")
    else:
        for errors in form.errors.values():
            for e in errors:
                flash(e, "danger")
    return redirect(url_for("main.settings"))


@bp.route("/avatars/<int:user_id>")
@login_required
def user_avatar(user_id):
    user = db.session.get(User, user_id)
    if user is None or not user.avatar_data:
        abort(404)
    return Response(
        user.avatar_data,
        mimetype=user.avatar_mimetype or "image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@bp.route("/avatar/delete", methods=["POST"])
@login_required
def delete_avatar():
    if current_user.avatar_data or current_user.avatar:
        remove_legacy_avatar_file(current_user.avatar)
        current_user.avatar_data = None
        current_user.avatar_mimetype = None
        current_user.avatar = None
        db.session.commit()
        flash("Аватар удалён.", "info")
    return redirect(url_for("main.settings"))
