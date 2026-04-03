#!/bin/sh
# Ajusta permissões em volumes montados
chown -R appuser:appuser /app/data /app/static/logos 2>/dev/null || true
# Executa como appuser
exec runuser -u appuser -- gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 60 --max-requests 1000 --max-requests-jitter 100 --access-logfile - app:app
