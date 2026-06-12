# =============================================================================
# AskGovRAGBot Container Specification
# =============================================================================
# This Dockerfile defines the build instructions to package the AskGovRAGBot application
# into a secure, minimized container image utilizing a multi-stage-like approach
# (caching dependency layers) to optimize build times and layer counts.
#
# Base Image:
# -----------
# - python:3.12-slim (Debian-based minimal Python footprint)
#
# Production configurations:
# --------------------------
# - Runs on port 8000.
# - Leverages gunicorn/uvicorn ASGI server for multi-worker scaling.
# - Sets non-root user execution context for enhanced runtime security.
# =============================================================================

FROM python:3.12-slim

# Set environment system configurations
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Set working directory context
WORKDIR /app

# Install system dependencies needed for compiling C-extensions if any
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to exploit Docker layer caching
COPY requirements.txt .

# Install dependencies into global site-packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all application source codes and frontend static assets
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Create a non-root system user and adjust file ownerships for safety
RUN useradd -u 8888 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port 8000 for standard web traffic
EXPOSE 8000

# Execute healthcheck status validation
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/metrics || exit 1

# Start the FastAPI application with Uvicorn ASGI runner
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
