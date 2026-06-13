# SwiftPDF Deployment Guide

This guide reflects the current Flask + SQLite application. SwiftPDF does not require a separate database service today; it stores runtime data in SQLite under the package instance directory.

## Local Docker Compose

1. Copy the environment file:

```bash
cp .env.example .env
```

2. Set `SWIFTPDF_SECRET_KEY` to a strong random value.

3. Start the stack:

```bash
docker compose up -d --build
```

4. Open `http://localhost:5000`.

The `swiftpdf-instance` Docker volume stores the SQLite database.

## Ubuntu VPS With Nginx

Install Docker:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Deploy:

```bash
git clone <repository-url> /opt/swiftpdf
cd /opt/swiftpdf
cp .env.example .env
```

Edit `.env`:

```env
SWIFTPDF_SECRET_KEY=<strong-random-secret>
SWIFTPDF_COOKIE_SECURE=1
```

Run:

```bash
docker compose up -d --build
```

Nginx reverse proxy:

```nginx
server {
    listen 80;
    server_name pdf.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name pdf.example.com;
    client_max_body_size 200M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Use Certbot or your platform certificate manager for TLS.

## AWS EC2

Recommended baseline:

- Ubuntu EC2 instance
- Security group allowing 22, 80, and 443
- Docker Compose deployment as above
- Nginx and Let's Encrypt on the host
- Regular backup of the `swiftpdf-instance` volume

## Future Kubernetes Readiness

Before Kubernetes production use, plan for:

- External secret management for `SWIFTPDF_SECRET_KEY`
- A persistent volume or managed database migration for SQLite data
- Separate ingress TLS configuration
- Resource requests and limits for LibreOffice-heavy conversions

## Backups

For Compose volumes, inspect the volume mount and back up the SQLite file regularly:

```bash
docker volume inspect swiftpdf_swiftpdf-instance
docker compose exec swiftpdf python -m sqlite3 /app/src/SwiftPDF/instance/swiftpdf.sqlite3 ".backup '/tmp/swiftpdf-backup.sqlite3'"
```

## Production Checklist

- [ ] Strong `SWIFTPDF_SECRET_KEY`
- [ ] `SWIFTPDF_COOKIE_SECURE=1` behind HTTPS
- [ ] Nginx `client_max_body_size` at least 100M
- [ ] Persistent SQLite volume backed up
- [ ] LibreOffice conversion tested
- [ ] Login, registration, forgot password, admin user management, premium expiry editing, and PDF tools smoke-tested
