web: gunicorn -w 2 -b 0.0.0.0:$PORT wsgi:app
release: FLASK_APP=run.py flask db upgrade
