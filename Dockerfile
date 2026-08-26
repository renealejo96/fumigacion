# Multi-stage / optimized Python slim container
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies required for psycopg2 and compiling packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install python dependencies first for layer caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . /app/

# Ensure uploads directory exists and entrypoint script has execution rights
RUN mkdir -p /app/uploads && \
    chmod +x /app/entrypoint.sh

# Expose internal Flask/Gunicorn port
EXPOSE 5000

# Run entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
