#!/usr/bin/env bash
set -e

python -c "from app import app, ensure_default_admin; app.app_context().push(); ensure_default_admin()"
exec gunicorn --bind 0.0.0.0:${PORT:-10000} app:app
