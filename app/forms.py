from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import (
    StringField, PasswordField, SubmitField, TextAreaField,
    SelectField, DateField, TimeField, BooleanField,
)
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, ValidationError, Optional,
)

from app.models import User


class RegistrationForm(FlaskForm):
    username = StringField("Имя", validators=[DataRequired(), Length(2, 64)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField(
        "Повторите пароль",
        validators=[DataRequired(), EqualTo("password", message="Пароли не совпадают")],
    )
    submit = SubmitField("Зарегистрироваться")

    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("Это имя уже занято.")

    def validate_email(self, field):
        email = field.data.strip().lower()
        field.data = email
        if User.query.filter_by(email=email).first():
            raise ValidationError("Этот email уже зарегистрирован.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    remember = BooleanField("Запомнить меня")
    submit = SubmitField("Войти")

    def validate_email(self, field):
        field.data = field.data.strip().lower()


class AvatarForm(FlaskForm):
    avatar = FileField("Фото профиля", validators=[
        FileRequired(message="Выберите файл"),
        FileAllowed(["png", "jpg", "jpeg", "gif", "webp"], "Только изображения"),
    ])
    submit = SubmitField("Загрузить")


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField("Текущий пароль", validators=[DataRequired()])
    new_password = PasswordField("Новый пароль", validators=[DataRequired(), Length(min=6)])
    new_password2 = PasswordField(
        "Повторите новый пароль",
        validators=[DataRequired(), EqualTo("new_password", message="Пароли не совпадают")],
    )
    submit = SubmitField("Сменить пароль")


class TimezoneForm(FlaskForm):
    timezone = SelectField("Часовой пояс", choices=[], validators=[DataRequired()])
    submit = SubmitField("Сохранить")


class EventForm(FlaskForm):
    """Создание личного дела."""

    title = StringField("Тема", validators=[DataRequired(), Length(1, 140)])
    description = TextAreaField("Описание", validators=[Optional()])
    date = DateField("Дата", validators=[DataRequired()])
    start_time = TimeField("Начало", validators=[DataRequired()])
    end_time = TimeField("Окончание", validators=[DataRequired()])
    submit = SubmitField("Сохранить")

    def validate_end_time(self, field):
        if self.start_time.data and field.data and field.data == self.start_time.data:
            raise ValidationError("Окончание должно отличаться от начала.")


class MeetingForm(FlaskForm):
    """Создание встречи с другим пользователем."""

    to_user = SelectField("С кем", coerce=int, validators=[DataRequired()])
    date = DateField("Дата", validators=[DataRequired()])
    start_time = TimeField("Время", validators=[DataRequired()])
    end_time = TimeField("Окончание", validators=[DataRequired()])
    title = StringField("Тема", validators=[DataRequired(), Length(1, 140)])
    description = TextAreaField("Описание", validators=[Optional()])
    submit = SubmitField("Отправить запрос")

    def validate_end_time(self, field):
        if self.start_time.data and field.data and field.data == self.start_time.data:
            raise ValidationError("Окончание должно отличаться от начала.")
