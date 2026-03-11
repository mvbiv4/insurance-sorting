FROM python:3.12-slim

# Install Tesseract OCR + OpenCV system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt waitress

# Copy application code
COPY run.py .
COPY src/ src/

# Create directories for persistent data
RUN mkdir -p /app/data /app/config /app/reports /app/logs /app/scans

# Copy default blocklist (will be overridden by volume mount)
COPY config/ config/

# Entrypoint initializes DB once at startup
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]

# Web dashboard port
EXPOSE 5000

# Volumes for persistent data
VOLUME ["/app/data", "/app/config", "/app/reports", "/app/scans"]

# Default: run web dashboard with waitress
CMD ["python", "run.py", "web", "--host", "0.0.0.0", "--port", "5000"]
