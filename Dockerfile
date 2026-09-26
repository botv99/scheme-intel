FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install curl and sqlite3 for health checks and database inspection
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and configuration
COPY src/ ./src/
COPY config/ ./config/
COPY data/ ./data/

# Expose HTTP port for container health probes (Railway, Render, Fly.io, etc.)
EXPOSE 8080

# Health check using the unified operational service health probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -m scheme_intel.delivery.service --health || exit 1

# Default command runs unified service (Telegram poller + Research queue worker)
CMD ["python", "-m", "scheme_intel.delivery.service", "--mode", "all"]
