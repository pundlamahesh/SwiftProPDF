# SwiftProPDF

SwiftProPDF is a Flask-based PDF toolkit with a public home page, guest-friendly tool access, user accounts, usage quotas, premium/admin roles, and an admin dashboard for user and quota management.

## Features

- Public home page with a tools grid and individual tool pages
- PDF tools: unlock, merge, split, compress, PDF to Word, PDF to Excel, PDF to PowerPoint, PDF to images, images to PDF, Office to PDF, rotate PDF, delete PDF pages, and QR code generation
- Guest, Free, Premium, and Admin account modes
- Weekly quota tracking for guests and Free users
- Premium/Admin unlimited usage
- Admin dashboard with user editing, deletion, role/status management, quota settings, analytics, audit logs, security-question status, and premium expiry management
- Forgot Password flow using fixed verification questions

## Authentication And Roles

SwiftProPDF supports four access levels:

- Guest users can use public tools with the guest weekly quota.
- Free users can register, sign in, and use the Free weekly quota.
- Premium users have unlimited conversions and no admin access.
- Admin users have unlimited conversions and access to the Admin Dashboard.

Passwords are hashed with Werkzeug password hashing. New registrations must also configure two password recovery answers:

- Date of Birth
- Which city are you currently living in?

Recovery answers are normalized, hashed, and stored in `user_security_questions`; plaintext answers are never stored.

Email OTP password recovery is not currently enabled. The forgot-password page uses the verification-question workflow.

## Weekly Quotas

Defaults are initialized in the application settings table:

- Guest: 5 executions per week
- Free: 10 executions per week
- Premium: unlimited
- Admin: unlimited

Admins can update weekly limits and reset quota counters from the Admin Dashboard.

## Admin Dashboard

The Admin Dashboard includes:

- User Management: add/edit users, update role/status, view weekly usage, and delete users with confirmation
- Premium Management: edit premium validity dates and view Premium Valid Until in the user grid
- Quota Management: guest/free/premium weekly limits and reset controls
- Analytics: total users, premium users, weekly conversions, and audit-event counts
- Security Visibility: whether recovery questions are configured, without exposing answers or hashes
- Audit Logs: login, registration, reset, tool, and admin actions

## Local Setup

Requirements:

- Python 3.9+
- LibreOffice for Office document conversion

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

## Configuration

Create `.env` from `.env.example`.

Required in production:

```env
SWIFTPROPDF_SECRET_KEY=replace-with-a-strong-random-secret
SWIFTPROPDF_COOKIE_SECURE=1
```

`SWIFTPROPDF_COOKIE_SECURE=1` requires HTTPS.

The app uses PostgreSQL when `DATABASE_URL` is set. Docker Compose starts a PostgreSQL service automatically and points both the web app and Celery worker at it. If `DATABASE_URL` is not set, the auth layer can still fall back to SQLite for lightweight local tests.

## Antivirus Scanning

SwiftProPDF can scan uploaded files with ClamAV before PDF, image, or Office parsers process them.

```env
CLAMAV_ENABLED=1
CLAMAV_HOST=clamav
CLAMAV_PORT=3310
```

Docker Compose starts a `clamav` service and enables scanning for both the web app and Celery worker. For local non-Docker development, keep `CLAMAV_ENABLED=0` unless you have `clamd` running locally.

## Database Migrations

SwiftProPDF uses Alembic migrations for schema creation and upgrades. Startup calls `init_db`, which applies migrations automatically before seeding settings and normalizing existing user data.

Manual migration command:

```bash
alembic upgrade head
```

## Docker

Build and run:

```bash
docker compose up --build
```

The app listens on `http://localhost:8000`. The compose file starts the web app, PostgreSQL, Redis, ClamAV, and a Celery worker. PostgreSQL data is persisted with the `swiftpropdf-postgres` volume, Redis state with `swiftpropdf-redis`, ClamAV definitions with `swiftpropdf-clamav`, and generated background-job files with `swiftpropdf-instance`.

## Background Processing

SwiftProPDF supports both processing modes:

- Normal mode: `SWIFTPROPDF_ASYNC_TOOLS=0`
  The existing Flask routes process each upload and return the generated file directly.
- Async mode: `SWIFTPROPDF_ASYNC_TOOLS=1`
  Tool form submissions are queued through Celery, Redis stores broker/result state, the browser polls job status, and the finished file downloads when ready.

Set `SWIFTPROPDF_ASYNC_WORKER_CONCURRENCY` to control how many Celery worker processes run async tool jobs. It defaults to `2` to keep CPU usage predictable.

Docker Compose enables async mode automatically. Local development can keep normal mode unless Redis and a Celery worker are running.

## VPS Deployment

For Ubuntu/Nginx:

1. Install Docker and Docker Compose.
2. Copy `.env.example` to `.env`, set a strong `SWIFTPROPDF_SECRET_KEY`, and set `SWIFTPROPDF_COOKIE_SECURE=1`.
3. Run `docker compose up -d --build`.
4. Put Nginx in front of `127.0.0.1:8000`.
5. Enable HTTPS with Let's Encrypt.
6. Back up the persistent PostgreSQL volume regularly.

Nginx proxy sketch:

```nginx
server {
    listen 443 ssl;
    server_name pdf.example.com;
    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Cloud Deployment

AWS EC2 deployment follows the VPS path: Docker, Compose, Nginx, HTTPS, and volume backups. Future Kubernetes readiness mainly requires pointing `DATABASE_URL` at managed PostgreSQL, using managed Redis, and externalizing secrets.

## Tests

```bash
python -m pip install -e . pytest
python -m pytest
```

The test suite covers schema migration startup, auth/session behavior, and deterministic PDF/image tool operations.

## Project Structure

```text
src/SwiftProPDF/
  auth.py          Authentication, users, quotas, audit events
  database.py      PostgreSQL connection adapter with SQLite fallback
  core.py          Compatibility exports for document tools
  tools/           One module per PDF, image, Office, and QR task
  email_otp.py     SMTP/SES helper functions; not active for password recovery
  web.py           Compatibility entry point for the Flask app
  web_app/         Flask app factory, web configuration, and tool catalog
  static/          Organized CSS, JavaScript, and image assets
  templates/       Grouped HTML templates by feature area
migrations/        Alembic database migrations
tests/             Core, migration, CLI, and auth tests
```
## Email Config

```text
to make support email to work we need to make 2 more entries in Route 53

one TXt type record and one MX type record
name : <blank>
recordtype = TXT
value = "v=spf1 include:_spf.google.com ~all"

name : <blank>
recordtype:MX
value : 1 SMTP.GOOGLE.COM
```
