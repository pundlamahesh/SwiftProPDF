# SwiftProPDF Setup

## Requirements

- Python 3.9+
- LibreOffice for Office document conversion
- Modern browser

## Python Setup

```bash
git clone <repository-url>
cd SwiftProPDF
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
swiftpropdf-ui
```

macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
swiftpropdf-ui
```

Open `http://127.0.0.1:5000`.

## Docker Setup

```bash
cp .env.example .env
docker compose up --build
```

Open `http://127.0.0.1:5000`.

## Configuration

Important environment variables:

- `SWIFTPROPDF_SECRET_KEY`: Flask session signing secret.
- `SWIFTPROPDF_COOKIE_SECURE`: set to `1` when served over HTTPS.
- `DATABASE_URL`: PostgreSQL connection URL.
- `REDIS_URL`: Redis connection URL for Celery.
- `SWIFTPROPDF_ASYNC_TOOLS`: set to `1` to use Redis/Celery background processing.
- `CLAMAV_ENABLED`: set to `1` to scan uploaded files with ClamAV before processing.
- `CLAMAV_HOST` / `CLAMAV_PORT`: ClamAV daemon connection settings.

Docker Compose starts ClamAV and enables scanning automatically. For local Python-only development, keep `CLAMAV_ENABLED=0` unless `clamd` is running on your machine.

The app creates and migrates PostgreSQL tables automatically at startup when `DATABASE_URL` is set.
SQLite fallback databases are migrated the same way when no PostgreSQL URL is configured.

Manual migration command:

```bash
alembic upgrade head
```

## First Run

1. Open the home page.
2. Register an account.
3. Registration requires Date of Birth and Current City for password recovery.
4. The first user is promoted to Admin automatically if no admin exists.
5. Visit `/admin` to manage users, quotas, premium validity, and audit logs.

## Tests

```bash
python -m pip install -e . pytest
python -m pytest
```

Tests cover database migrations, authentication/session behavior, and core PDF/image tools.

## Troubleshooting

- LibreOffice conversion errors: install LibreOffice and verify `libreoffice --version`.
- Port 5000 already in use: stop the existing process or run `swiftpropdf-ui --port 8001`.
- Forgot Password unavailable for existing accounts: sign in and configure Security Questions in Account Settings.
- Premium expiry not shown: verify the user role is Premium and the Premium Valid Until date is set in Admin edit mode.
