from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import User, Organization
from app.forms import RegistrationForm, LoginForm
from app.helpers import rate_limit, apply_bootstrap_admin_role, record_failed_login
from app.routes import bp


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.calendar"))
    form = RegistrationForm()
    if form.validate_on_submit():
        org = Organization.query.first()
        user = User(
            username=form.username.data,
            email=form.email.data,
            organization_id=org.id if org else None,
            role="member",
            timezone=current_app.config.get("DEFAULT_USER_TIMEZONE", "Europe/Moscow"),
        )
        user.set_password(form.password.data)
        apply_bootstrap_admin_role(user)
        db.session.add(user)
        db.session.commit()
        flash("Регистрация прошла успешно. Теперь войдите.", "success")
        return redirect(url_for("main.login"))
    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@rate_limit("login")
def login():
    if current_user.is_authenticated and request.method == "GET":
        return redirect(url_for("main.calendar"))
    form = LoginForm()
    if form.validate_on_submit():
        if current_user.is_authenticated:
            logout_user()
        user = User.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            record_failed_login("login")
            flash("Неверный email или пароль.", "danger")
            return redirect(url_for("main.login"))
        apply_bootstrap_admin_role(user)
        db.session.commit()
        login_user(user, remember=form.remember.data)
        return redirect(url_for("main.calendar"))
    return render_template("login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))
