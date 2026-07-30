# Quantoryx — Railway Production Dockerfile
# Python 3.12 slim base for a lean, reproducible build
FROM python:3.12-slim

# Prevents Python from writing .pyc files and enables unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security
RUN groupadd --gid 1001 quantoryx && \
    useradd --uid 1001 --gid quantoryx --shell /bin/bash --create-home quantoryx

# Set working directory
WORKDIR /app

# Install system dependencies required for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application source code
COPY . .

# Create the workspace directories the app needs at runtime
RUN mkdir -p data output/optimization output/trades reports logs config/optimized && \
    chown -R quantoryx:quantoryx /app

# Switch to non-root user
USER quantoryx

# Railway injects $PORT at runtime; default to 8000 for local runs
ENV PORT=8000

# Health-check so Railway knows when the container is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/api/health')" || exit 1

# Start the FastAPI application via uvicorn
# --host 0.0.0.0 is mandatory on Railway (not 127.0.0.1)
# $PORT is provided by Railway's runtime environment
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info
