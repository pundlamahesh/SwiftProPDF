# SwiftProPDF Deployment Guide

This guide reflects the current Flask + PostgreSQL application. Docker Compose starts PostgreSQL for account, quota, audit, and session data, Redis for Celery, and a Celery worker for background file processing.

## Local Docker Compose

1. Copy the environment file:

```bash
cp .env.example .env
```

2. Set `SWIFTPROPDF_SECRET_KEY` to a strong random value.

3. Start the stack:

```bash
docker compose up -d --build
```

4. Open `http://localhost:8000`.

The Compose stack starts the web app, PostgreSQL, Redis, and a Celery worker. The `swiftpropdf-postgres` Docker volume stores database data; `swiftpropdf-instance` stores generated background-job files.

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
git clone <repository-url> /opt/swiftpropdf
cd /opt/swiftpropdf
cp .env.example .env
```

Edit `.env`:

```env
SWIFTPROPDF_SECRET_KEY=<strong-random-secret>
SWIFTPROPDF_COOKIE_SECURE=1
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
        proxy_pass http://127.0.0.1:8000;
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
- Regular PostgreSQL backups and backup of generated job files if needed

## Future Kubernetes Readiness

Before Kubernetes production use, plan for:

- External secret management for `SWIFTPROPDF_SECRET_KEY`
- A managed PostgreSQL database or persistent PostgreSQL volume
- Separate ingress TLS configuration
- Resource requests and limits for LibreOffice-heavy conversions

## Backups

For Compose volumes, back up PostgreSQL regularly:

```bash
docker compose exec postgres pg_dump -U swiftpropdf swiftpropdf > swiftpropdf-backup.sql
```

## Production Checklist

- [ ] Strong `SWIFTPROPDF_SECRET_KEY`
- [ ] `SWIFTPROPDF_COOKIE_SECURE=1` behind HTTPS
- [ ] Nginx `client_max_body_size` at least 100M
- [ ] Persistent PostgreSQL volume backed up
- [ ] Redis/Celery worker healthy
- [ ] LibreOffice conversion tested
- [ ] Login, registration, forgot password, admin user management, premium expiry editing, and PDF tools smoke-tested
