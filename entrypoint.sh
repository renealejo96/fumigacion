#!/bin/sh
set -e

echo "================================================="
echo "  Starting AgroFumigacion Web Application"
echo "================================================="

# Wait for DB, create tables, create default admin and seed if needed
python init_db.py

# Determine listening port (Render provides dynamic $PORT)
APP_PORT="${PORT:-5000}"

# Execute Gunicorn WSGI server
echo "Starting Gunicorn server on port ${APP_PORT}..."
exec gunicorn --bind "0.0.0.0:${APP_PORT}" \
    --workers ${GUNICORN_WORKERS:-2} \
    --threads ${GUNICORN_THREADS:-2} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    --error-logfile - \
    "run:app"
