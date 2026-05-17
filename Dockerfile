# ==============================================================================
# 🐳 WebScraper.pro — Dockerfile for Hugging Face Free Spaces
# ==============================================================================
# This Dockerfile is highly optimized for Hugging Face Spaces:
# 1. Uses the official Playwright base image matching playwright==1.44.0
# 2. Runs as a secure, non-root user (UID 1000) as required by HF Spaces
# 3. Ensures write access for SQLite database, logs, and scraped exports
# 4. Serves the Flask app via Gunicorn on the standard HF Space port (7860)
# ==============================================================================

# Use official Playwright Python image. The jammy tag is based on Ubuntu Jammy.
# The version v1.44.0-jammy perfectly matches the playwright version in requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Set shell to bash and enable pipefail
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Set environment variables for Python, Flask, and Playwright
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=run.py \
    FLASK_ENV=production \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=7860

# Install additional utility system packages if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set up the working directory inside the container
WORKDIR /app

# Install Python packages
# We copy requirements.txt separately to leverage Docker build cache
COPY requirements.txt /app/
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# Leverage the pre-created 'pwuser' user (UID 1000) already defined in the official Playwright image
# This prevents UID collision errors during useradd and complies with HF Spaces UID 1000 requirement.
RUN mkdir -p /app/database /app/logs /app/exports && \
    chown -R 1000:1000 /app

# Ensure that the Playwright browser files are fully readable/executable by the non-root user.
# In the official Playwright image, browsers are stored in /ms-playwright.
RUN chmod -R 755 /ms-playwright

# Copy the rest of the application files to the container and set ownership to UID 1000 (pwuser)
COPY --chown=1000:1000 . /app

# Switch to the non-root user (UID 1000)
USER 1000

# Expose the default port expected by Hugging Face Spaces (7860)
EXPOSE 7860

# Define the command to start the application using Gunicorn
# - --bind 0.0.0.0:7860: Listens on all interfaces on the Hugging Face port
# - --workers 2: Employs 2 worker processes (optimal for HF's 2-vCPU free tier)
# - --timeout 120: High timeout because web scraping tasks can take longer to load/process
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "2", "--timeout", "120", "run:app"]
