#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Superuser avtomatik yaratiladi (Render bepul tarifda Shell yo'q).
# Allaqachon bor bo'lsa xato bermaydi.
python manage.py createsuperuser --noinput || true  