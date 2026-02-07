# Use official Playwright image which has Python and browsers
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Set working directory
WORKDIR /app

# Install system dependencies (Playwright image has most, but we might need some extras)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Playwright browsers are already installed in this image, 
# but we need to ensuring our specific version matches or is compatible.
# The base image comes with browsers for its playwright version.
# We'll run install just in case the requirement version differs slightly
RUN playwright install chromium
# RUN playwright install-deps chromium # Not needed, base image has them


# Copy application code
COPY . .

# Create log directories
RUN mkdir -p logs/screenshots logs/html

# Expose port
EXPOSE 8000

# Run the application
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
