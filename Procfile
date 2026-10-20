web: FLASK_ENV=production gunicorn -w 2 -b 0.0.0.0:$PORT wsgi:app
release: FLASK_ENV=production FLASK_APP=run.py flask db upgrade
