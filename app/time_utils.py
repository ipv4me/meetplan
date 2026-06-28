"""Часовые пояса: хранение в UTC (naive), отображение в локальном."""

from datetime import datetime, time as dt_time, timedelta, timezone, date
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Europe/Moscow"

MONTHS_RU = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)

TIMEZONE_CHOICES = [
    ("Europe/Moscow", "Москва (UTC+3)"),
    ("Europe/Kaliningrad", "Калининград (UTC+2)"),
    ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
    ("Asia/Novosibirsk", "Новосибирск (UTC+7)"),
    ("Asia/Vladivostok", "Владивосток (UTC+10)"),
    ("UTC", "UTC"),
    ("Europe/London", "Лондон"),
    ("Europe/Berlin", "Берлин"),
    ("America/New_York", "Нью-Йорк"),
]


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_iso(dt):
    """Naive UTC datetime → ISO 8601 с суффиксом Z для FullCalendar."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def event_local_iso(dt, tz):
    """Naive UTC → локальное wall-clock ISO без Z (для FullCalendar с named timeZone)."""
    if dt is None:
        return None
    return utc_to_local(dt, tz).strftime("%Y-%m-%dT%H:%M:%S")


def user_timezone_name(user):
    if user is None:
        return DEFAULT_TIMEZONE
    return getattr(user, "timezone", None) or DEFAULT_TIMEZONE


def local_today(user):
    return utc_to_local(utcnow(), user_timezone(user)).date()


def task_block_utc(task, user):
    """Локальные due_date/due_time задачи → интервал UTC (для конфликтов с событиями в БД)."""
    start_t = task.due_time or dt_time(9, 0)
    local_start = datetime.combine(task.due_date, start_t)
    utc_start = local_to_utc(local_start, user_timezone(user))
    return utc_start, utc_start + timedelta(hours=1)


def task_block_local_iso(task):
    """Локальные due_date/due_time → ISO без Z для FullCalendar (wall-clock в поясе пользователя)."""
    start_t = task.due_time or dt_time(9, 0)
    local_start = datetime.combine(task.due_date, start_t)
    local_end = local_start + timedelta(hours=1)
    fmt = "%Y-%m-%dT%H:%M:%S"
    return local_start.strftime(fmt), local_end.strftime(fmt)


def timezone_label(name):
    for tz_id, label in TIMEZONE_CHOICES:
        if tz_id == name:
            return label
    return name or DEFAULT_TIMEZONE


def resolve_tz(name):
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


def user_timezone(user):
    if user is None:
        return resolve_tz(DEFAULT_TIMEZONE)
    return resolve_tz(getattr(user, "timezone", None) or DEFAULT_TIMEZONE)


def local_to_utc(naive_local, tz):
    aware = naive_local.replace(tzinfo=tz)
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(naive_utc, tz):
    aware = naive_utc.replace(tzinfo=timezone.utc)
    return aware.astimezone(tz).replace(tzinfo=None)


def combine_user_local(date_value, time_value, user):
    tz = user_timezone(user)
    local = datetime.combine(date_value, time_value)
    return local_to_utc(local, tz)


def meeting_end_datetime(date_value, start_time, end_time):
    """Если окончание «раньше» начала — перенос на следующий день (23:00→00:00)."""
    start = datetime.combine(date_value, start_time)
    end = datetime.combine(date_value, end_time)
    if end <= start:
        end += __import__("datetime").timedelta(days=1)
    return start, end


def combine_user_meeting(date_value, start_time, end_time, user):
    start_local, end_local = meeting_end_datetime(date_value, start_time, end_time)
    tz = user_timezone(user)
    return local_to_utc(start_local, tz), local_to_utc(end_local, tz)


def format_month_year(dt, tz=None):
    local = utc_to_local(dt, tz) if tz else dt
    return f"{MONTHS_RU[local.month - 1]} {local.year}"


def parse_client_datetime(iso_str, user):
    """ISO от клиента: с Z — UTC, без — локальное время пользователя."""
    if not iso_str:
        raise ValueError("empty")
    s = iso_str.strip()
    if s.endswith("Z"):
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    if len(s) > 6 and s[10] in ("+", "-"):
        dt = datetime.fromisoformat(s)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    dt = datetime.fromisoformat(s)
    return local_to_utc(dt, user_timezone(user))


def format_dt(dt, user, fmt="%d.%m.%Y в %H:%M"):
    if dt is None:
        return ""
    local = utc_to_local(dt, user_timezone(user))
    return local.strftime(fmt)
