# Dockerfile for Wandering Inn Scraper

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY .env.example .env

# Set Python path
ENV PYTHONPATH=/app

# No default command - use 'docker-compose run scraper <command>' to execute specific tasks
# The scraper is designed for one-off commands, not as a long-running service
