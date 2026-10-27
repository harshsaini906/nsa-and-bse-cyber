# Production Dockerfile for TradingAI
FROM python:3.11-slim

# Prevent python from writing pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=5000

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure data directory exists
RUN mkdir -p /app/data

# Expose port
EXPOSE 5000

# Health check probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

# Start gunicorn production server
CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT:-5000} app:app --timeout 120"]
