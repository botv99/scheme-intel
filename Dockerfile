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

# Create application directories and non-root user (UID 1000 matches default Ubuntu VM user)
RUN useradd -m -u 1000 -s /bin/bash schemeintel && \
    mkdir -p /app/data /app/logs && \
    chown -R schemeintel:schemeintel /app

# Copy application code and configuration
COPY --chown=schemeintel:schemeintel src/ ./src/
COPY --chown=schemeintel:schemeintel config/ ./config/
COPY --chown=schemeintel:schemeintel data/ ./data/

# Switch to non-root user
USER schemeintel

# Expose HTTP port for container health probes
EXPOSE 8080

# Health check using the unified operational service health probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -m scheme_intel.delivery.service --health || exit 1

# Default command runs unified service (Telegram poller + Research worker + Snapshot syncer)
CMD ["python", "-m", "scheme_intel.delivery.service", "--mode", "all"]
