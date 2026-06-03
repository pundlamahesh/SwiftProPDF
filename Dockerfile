FROM python:3.11-slim

LABEL maintainer="SwiftPDF"
LABEL description="SwiftPDF - Professional PDF Tools Suite"

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
RUN useradd -m -u 1000 swiftpdf

# Set working directory
WORKDIR /app

# Copy application
COPY --chown=swiftpdf:swiftpdf . .

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install -e .

RUN pip install gunicorn

# Create runtime directories. The Flask app stores SQLite data under the package instance path.
RUN mkdir -p /app/src/SwiftPDF/instance /tmp/swiftpdf && \
    chown -R swiftpdf:swiftpdf /app/src/SwiftPDF/instance /tmp/swiftpdf

# Switch to non-root user
USER swiftpdf

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()" || exit 1

# Start application
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "--timeout", "300", "SwiftPDF.web:create_app()"]
