# MeetPlan

Информационная система планирования и согласования встреч пользователей
с календарным интерфейсом (дипломный проект).

**Стек:** Python · Flask · SQLAlchemy · SQLite/PostgreSQL · Bootstrap 5 · FullCalendar.js · jQuery

## Возможности

- Регистрация и авторизация
- Личный календарь (день / неделя / месяц / список), перетаскивание личных событий
- Задачи «Мои дела» с датой/временем в календаре и редактированием
- Встречи с согласованием, проверкой конфликтов, отменой обоими участниками
- Просмотр календаря коллег, поиск общих свободных слотов
- Администрирование (назначение админов через `ADMIN_EMAILS`)
- Адаптивный UI, тёмная тема, CSRF-защита AJAX

## Быстрый старт

```bash
cd meetplan
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # задайте SECRET_KEY и ADMIN_EMAILS
python run.py
```

Открыть: http://127.0.0.1:5001

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `SECRET_KEY` | Ключ сессий (обязателен в production) |
| `ADMIN_EMAILS` | Email владельца, всегда admin |
| `DATABASE_URL` | PostgreSQL или SQLite |
| `FLASK_ENV` | `production` на сервере |
| `FLASK_DEBUG` | `0` на сервере, `1` локально |
| `PORT` | Порт (по умолчанию 5001) |
| `DEFAULT_USER_TIMEZONE` | Пояс новых пользователей (по умолчанию `Europe/Moscow`) |
| `FLASK_APP` | `run.py` — для `flask db upgrade` |

## Деплой на Render + Neon

1. **Web Service** → Build: `pip install -r requirements.txt`, Start: `gunicorn -w 2 -b 0.0.0.0:$PORT wsgi:app`
2. **Environment** (Render → Environment):
   - `SECRET_KEY` — случайная строка
   - `ADMIN_EMAILS` — ваш email
   - `FLASK_ENV` = `production`
   - `DATABASE_URL` — строка подключения Neon (с `?sslmode=require`)
   - `FLASK_APP` = `run.py`
3. **Pre-Deploy Command** (опционально): `flask db upgrade`
4. Postgres на Render **не нужен**, если используете Neon.

При первом деплое таблицы создаются автоматически, если БД пустая.

## Production

```bash
gunicorn -w 2 -b 0.0.0.0:5001 wsgi:app
```

Или через Docker:

```bash
docker build -t meetplan .
docker run -p 5001:5001 -e SECRET_KEY=... -e ADMIN_EMAILS=you@mail.com meetplan
```

## Миграции БД

```bash
export FLASK_APP=run.py
flask db init          # один раз
flask db migrate -m "описание"
flask db upgrade
```

При первом запуске также работает `ensure_schema()` для совместимости со старыми БД.

## Тесты

```bash
pytest tests/ -q
```

## Структура

```
meetplan/
├── app/
│   ├── routes/          # auth, calendar, meetings, tasks, users, admin, …
│   ├── services/        # scheduling (конфликты, свободные слоты)
│   ├── templates/
│   ├── static/
│   ├── models.py
│   ├── helpers.py
│   └── time_utils.py
├── migrations/          # Flask-Migrate / Alembic
├── tests/
├── wsgi.py
├── run.py
├── Procfile
├── Dockerfile
└── config.py
```
