FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/production.txt

COPY . .

EXPOSE 8000
# collectstatic runs at container start, not build time — production settings
# require the Supabase S3 env vars just to load, and those are only ever
# available at runtime, never during `docker build`.
CMD ["sh", "-c", "python manage.py collectstatic --noinput --settings=config.settings.production && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
