# SwiftPDF Installation & Setup Guide

## System Requirements

### Minimum Requirements
- Python 3.9 or higher
- 2GB RAM
- 500MB disk space for application and temporary files
- Modern web browser

### Recommended Requirements
- Python 3.11+
- 4GB+ RAM
- 2GB disk space
- Linux/macOS (or Windows with WSL for best LibreOffice support)

### Optional Dependencies
- **LibreOffice** (for Word/Excel/PowerPoint to PDF conversion)
- **Ghostscript** (for advanced PDF compression - optional)

## Installation Steps

### 1. Clone the Repository

```bash
git clone <repository-url>
cd SwiftPDF
```

### 2. Create Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip setuptools wheel
pip install -e .
```

### 4. Install System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y libreoffice python3-pip
```

**Fedora/RHEL:**
```bash
sudo dnf install -y libreoffice python3-pip
```

**macOS (with Homebrew):**
```bash
brew install libreoffice
```

**Windows:**
Download and install from: https://www.libreoffice.org/download/

### 5. Verify Installation

```bash
# Test CLI
swiftpdf --help

# Test Web UI (will start server)
swiftpdf-ui
```

## Configuration

### Environment Setup

Create a `.env` file in the project root:

```bash
# Security
SWIFTPDF_SECRET_KEY=your-secret-key-here
FLASK_ENV=production

# File Upload Limits (in bytes, default: 100MB)
MAX_CONTENT_LENGTH=104857600

# Database Location
DATABASE_PATH=./instance/swiftpdf.sqlite3

# Temporary Files
TEMP_DIR=/tmp/swiftpdf

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/swiftpdf.log
```

### Generate Secret Key

```python
python -c "import secrets; print(secrets.token_hex(32))"
```

Use the output for `SWIFTPDF_SECRET_KEY`.

## Running the Application

### Web UI (Recommended)

```bash
# Default: localhost:5000
swiftpdf-ui

# Custom host/port
swiftpdf-ui --host 0.0.0.0 --port 8000
```

### Command Line

```bash
# Unlock a PDF
swiftpdf locked.pdf -o unlocked.pdf

# Split a PDF
swiftpdf input.pdf -o output.pdf --pages 1-5,10-15

# Get help
swiftpdf --help
```

## Database Setup

The application automatically initializes the SQLite database on first run.

To reset the database:
```bash
rm instance/swiftpdf.sqlite3
```

The database will be recreated on next application startup.

## Development Setup

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v
```

### Run Linting

```bash
flake8 src/SwiftPDF
black src/SwiftPDF --check
```

### Format Code

```bash
black src/SwiftPDF
```

## Troubleshooting

### Python Not Found

**Solution:** Ensure Python 3.9+ is installed and in PATH.

```bash
python --version
# or
python3 --version
```

### LibreOffice Not Found for Office Conversion

**Error:** `LibreOffice conversion failed. Is LibreOffice installed?`

**Solution:**
- Install LibreOffice (see System Dependencies section)
- Verify installation: `libreoffice --version`

### Permission Denied on Linux/macOS

```bash
chmod +x .venv/bin/swiftpdf-ui
```

### Port Already in Use

```bash
# Use different port
swiftpdf-ui --port 8001

# Or find and stop process using port 5000
# Linux/macOS:
lsof -i :5000
# Windows:
netstat -ano | findstr :5000
```

### Large File Upload Issues

If uploads fail for large files:

1. Increase `MAX_CONTENT_LENGTH` in `.env`
2. Check disk space: `df -h` (Linux/macOS) or `dir C:\` (Windows)
3. Check temporary directory permissions

### Memory Issues

If processing large PDFs causes memory errors:

1. Increase available RAM or reduce file size
2. Process files separately instead of in batch
3. Close other applications
4. Increase system swap space

### Database Locked Error

```bash
# Remove lock file (if exists)
rm instance/swiftpdf.sqlite3-shm
rm instance/swiftpdf.sqlite3-wal

# Restart application
swiftpdf-ui
```

## Docker Installation

### Build Docker Image

```bash
docker build -t swiftpdf .
```

### Run Docker Container

```bash
docker run -p 5000:5000 \
  -e SWIFTPDF_SECRET_KEY=your-secret-key \
  -v /tmp/swiftpdf:/tmp/swiftpdf \
  swiftpdf
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  swiftpdf:
    build: .
    ports:
      - "5000:5000"
    environment:
      SWIFTPDF_SECRET_KEY: ${SECRET_KEY}
      FLASK_ENV: production
    volumes:
      - ./instance:/app/instance
      - /tmp/swiftpdf:/tmp/swiftpdf
    restart: unless-stopped
```

Run with:
```bash
docker-compose up -d
```

## Performance Tuning

### For Large Files

1. Increase timeout:
   ```bash
   # Set appropriate timeout for your use case
   export SWIFTPDF_TIMEOUT=300
   ```

2. Monitor disk space:
   ```bash
   # Linux
   watch -n 5 'df -h | grep /tmp'
   ```

3. Monitor memory:
   ```bash
   # Linux
   watch -n 5 'free -h'
   ```

### Optimize Temporary Storage

```bash
# Use faster storage for temp directory
# Edit .env:
TEMP_DIR=/mnt/fast_ssd/swiftpdf
```

### Database Optimization

```python
# Run optimization (optional)
python
>>> import sqlite3
>>> conn = sqlite3.connect('instance/swiftpdf.sqlite3')
>>> conn.execute('VACUUM')
>>> conn.close()
```

## Production Deployment Checklist

- [ ] Change default `SWIFTPDF_SECRET_KEY`
- [ ] Set `FLASK_ENV=production`
- [ ] Configure firewall rules
- [ ] Setup HTTPS/TLS
- [ ] Configure backup for database
- [ ] Setup log rotation
- [ ] Configure rate limiting (if needed)
- [ ] Setup monitoring/alerting
- [ ] Configure backup for temporary files location
- [ ] Test all features
- [ ] Setup error logging/reporting
- [ ] Document custom configurations

## Uninstallation

```bash
# Remove virtual environment
rm -rf .venv

# Or with venv
deactivate
rm -rf /path/to/venv

# Uninstall package (if installed globally)
pip uninstall swiftpdf
```

## Next Steps

1. Start the Web UI: `swiftpdf-ui`
2. Register a user account
3. Begin using PDF tools
4. Check logs if any issues occur

For more information, see [README.md](README.md)
