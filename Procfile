release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
web: gunicorn hello_world.wsgi:application --bind 0.0.0.0:${PORT:-8000}
