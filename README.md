# MeetPlan

<p align="center">
  <strong>Планирование и согласование встреч с общим календарём</strong><br>
  Дипломный веб‑проект · Flask · FullCalendar · Bootstrap 5
</p>

<p align="center">
  <a href="https://meetplan-sei9.onrender.com">🚀 Демо</a> ·
  <a href="#быстрый-старт">Быстрый старт</a> ·
  <a href="#возможности">Возможности</a> ·
  <a href="#деплой">Деплой</a>
</p>

---

**MeetPlan** — информационная система для назначения встреч между пользователями: личный календарь, задачи, друзья, согласование приглашений и поиск общих свободных слотов.

| | |
|---|---|
| **Стек** | Python 3 · Flask · SQLAlchemy · Alembic · PostgreSQL / SQLite |
| **UI** | Bootstrap 5 · FullCalendar.js · jQuery |
| **Деплой** | Render + Neon · Gunicorn · Docker |

## Возможности

- **Календарь** — день / неделя / месяц / список; перетаскивание личных событий; клик по слоту создаёт событие
- **Встречи** — приглашения, подтверждение / отклонение, отмена обоими участниками, проверка конфликтов
- **Друзья** — поиск, заявки, пригласительная ссылка, просмотр календаря друга
- **Приватность** — скрытие деталей календаря глобально или для отдельного друга
- **Мои дела** — задачи с датой и временем, синхронизация с календарём
- **Свободное время** — общие свободные окна для встречи с другом
- **Профиль и настройки** — аватар, часовой пояс, тёмная тема, браузерные уведомления
- **Админка** — роли и сводная статистика (`ADMIN_EMAILS`)
- **Безопасность** — CSRF, rate limit на вход, ProxyFix / HTTPS в production

## Быстрый старт

```bash
git clone https://github.com/ipv4me/meetplan.git
cd meetplan
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # SECRET_KEY, ADMIN_EMAILS
python run.py
```

Откройте [http://127.0.0.1:5001](http://127.0.0.1:5001).

```bash
pytest tests/ -q   # 50+ регрессионных тестов
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `SECRET_KEY` | Ключ сессий (**обязателен** в production) |
| `DATABASE_URL` | PostgreSQL (Neon) или SQLite (**обязателен** в production) |
| `ADMIN_EMAILS` | Email владельца / админов через запятую |
| `FLASK_ENV` | `production` на сервере (Procfile выставляет сам) |
| `FLASK_DEBUG` | `1` локально, `0` на сервере |
| `PORT` | Порт (по умолчанию `5001`) |
| `DEFAULT_USER_TIMEZONE` | Пояс новых пользователей (`Europe/Moscow`) |
| `FLASK_APP` | `run.py` для миграций |

Пример: [`.env.example`](.env.example).

## Деплой

### Render + Neon

1. **Web Service** → Build: `pip install -r requirements.txt`  
   Start: `gunicorn -w 2 -b 0.0.0.0:$PORT wsgi:app`
2. **Environment:** `SECRET_KEY`, `ADMIN_EMAILS`, `DATABASE_URL` (Neon, `?sslmode=require`), `FLASK_APP=run.py`
3. **Release** (Procfile): `flask db upgrade`
4. Отдельный Postgres на Render не нужен, если БД в Neon

### Docker

```bash
docker build -t meetplan .
docker run -p 5001:5001 \
  -e SECRET_KEY=... \
  -e ADMIN_EMAILS=you@mail.com \
  -e DATABASE_URL=... \
  meetplan
```

## Структура

```
meetplan/
├── app/
│   ├── routes/           # auth, calendar, meetings, tasks, users, admin…
│   ├── services/         # конфликты и свободные слоты
│   ├── templates/ · static/
│   ├── models.py · forms.py · helpers.py
│   ├── friends_service.py · time_utils.py · utils.py
├── migrations/           # Alembic
├── tests/
├── wsgi.py · run.py · Procfile · Dockerfile
└── config.py
```

## Лицензия

Учебный дипломный проект. Использование кода — по согласованию с автором.
