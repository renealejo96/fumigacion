#!/bin/sh
set -e

echo "================================================="
echo "  Starting AgroFumigacion Web Application"
echo "================================================="

# Wait for DB, create tables, create default admin and seed if needed
python init_db.py

# Execute Gunicorn WSGI server
echo "Starting Gunicorn server on port 5000..."
exec gunicorn --bind 0.0.0.0:5000 \
    --workers ${GUNICORN_WORKERS:-3} \
    --threads ${GUNICORN_THREADS:-2} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    --error-logfile - \
    "run:app"
