#!/usr/bin/env bash
# exit on error
set -o errexit

# Install production dependencies
pip install -r requirements/production.txt

# Collect static files
python manage.py collectstatic --no-input

# Run database migrations
python manage.py migrate
