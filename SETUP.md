# SwiftPDF Setup

## Requirements

- Python 3.9+
- LibreOffice for Office document conversion
- Modern browser

## Python Setup

```bash
git clone <repository-url>
cd SwiftPDF
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
swiftpdf-ui
```

macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
swiftpdf-ui
```

Open `http://127.0.0.1:5000`.

## Docker Setup

```bash
cp .env.example .env
docker compose up --build
```

Open `http://127.0.0.1:5000`.

## Configuration

Only these environment variables are currently used by the app:

- `SWIFTPDF_SECRET_KEY`: Flask session signing secret.
- `SWIFTPDF_COOKIE_SECURE`: set to `1` when served over HTTPS.

The app creates and migrates SQLite automatically at startup.

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

## Troubleshooting

- LibreOffice conversion errors: install LibreOffice and verify `libreoffice --version`.
- Port 5000 already in use: stop the existing process or run `swiftpdf-ui --port 8001`.
- Forgot Password unavailable for existing accounts: sign in and configure Security Questions in Account Settings.
- Premium expiry not shown: verify the user role is Premium and the Premium Valid Until date is set in Admin edit mode.
