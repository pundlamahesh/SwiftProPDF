FROM python:3.11-slim

LABEL maintainer="SwiftProPDF"
LABEL description="SwiftProPDF - Professional PDF Tools Suite"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    ghostscript \
    libmagic1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Create application user
RUN useradd -m -u 1000 swiftpropdf

# Set working directory
WORKDIR /app

# Copy application
COPY --chown=swiftpropdf:swiftpropdf . .

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install -e .

RUN pip install gunicorn

# Create runtime directories. The Flask app stores SQLite data under the package instance path.
RUN mkdir -p /app/src/SwiftProPDF/instance /tmp/swiftpropdf && \
    chown -R swiftpropdf:swiftpropdf /app/src/SwiftProPDF/instance /tmp/swiftpropdf

# Switch to non-root user
USER swiftpropdf

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()" || exit 1

# Start application
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "--timeout", "300", "SwiftProPDF.web:create_app()"]
