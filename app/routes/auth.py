from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import User
from app.forms import RegistrationForm, LoginForm
from app.helpers import rate_limit, apply_bootstrap_admin_role, record_failed_login, safe_redirect_target
from app.routes import bp


def _normalize_email(email):
    return (email or "").strip().lower()


@bp.route("/register", methods=["GET", "POST"])
@rate_limit("register")
def register():
    if current_user.is_authenticated and request.method == "GET":
        return redirect(safe_redirect_target())
    form = RegistrationForm()
    if form.validate_on_submit():
        if current_user.is_authenticated:
            logout_user()
        email = _normalize_email(form.email.data)
        user = User(
            username=form.username.data.strip(),
            email=email,
            role="member",
            timezone=current_app.config.get("DEFAULT_USER_TIMEZONE", "Europe/Moscow"),
        )
        user.set_password(form.password.data)
        user.ensure_invite_token()
        apply_bootstrap_admin_role(user)
        db.session.add(user)
        db.session.commit()
        login_user(user, remember=True)
        flash("Добро пожаловать в MeetPlan!", "success")
        return redirect(safe_redirect_target())
    if request.method == "POST" and form.errors:
        record_failed_login("register")
    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@rate_limit("login")
def login():
    if current_user.is_authenticated and request.method == "GET":
        return redirect(safe_redirect_target())
    form = LoginForm()
    if form.validate_on_submit():
        if current_user.is_authenticated:
            logout_user()
        email = _normalize_email(form.email.data)
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(form.password.data):
            record_failed_login("login")
            flash("Неверный email или пароль.", "danger")
            nxt = request.form.get("next")
            return redirect(url_for("main.login", next=nxt) if nxt else url_for("main.login"))
        apply_bootstrap_admin_role(user)
        db.session.commit()
        login_user(user, remember=form.remember.data)
        return redirect(safe_redirect_target())
    return render_template("login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))
