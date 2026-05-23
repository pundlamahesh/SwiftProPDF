# SwiftPDF Deployment Guide

## Production Deployment

This guide covers deploying SwiftPDF to a production environment.

## Architecture Overview

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTPS
┌──────▼────────────┐
│  Nginx/Apache     │  (Reverse Proxy)
└──────┬────────────┘
       │ HTTP (127.0.0.1)
┌──────▼──────────────────┐
│   SwiftPDF App          │
│  (Python/Flask)         │
├─────────────────────────┤
│  - Core processing      │
│  - User management      │
│  - File handling        │
└──────┬──────────────────┘
       │
┌──────▼──────────────────┐
│  SQLite Database        │
│  Temporary Files        │
└─────────────────────────┘
```

## Prerequisites

- Ubuntu 20.04 LTS (or similar Linux)
- Python 3.11+
- Nginx or Apache
- LibreOffice
- 2GB+ RAM
- 10GB+ disk space
- SSH access for deployment

## Step 1: System Setup

### Update System

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### Install System Dependencies

```bash
sudo apt-get install -y \
  python3.11 \
  python3.11-venv \
  python3-pip \
  libreoffice \
  nginx \
  git \
  curl \
  build-essential \
  libssl-dev \
  libffi-dev \
  python3.11-dev
```

### Create Application User

```bash
sudo useradd -m -s /bin/bash swiftpdf
sudo usermod -aG www-data swiftpdf
```

## Step 2: Application Setup

### Clone Repository

```bash
sudo -u swiftpdf git clone <repository-url> /opt/swiftpdf
cd /opt/swiftpdf
```

### Create Virtual Environment

```bash
sudo -u swiftpdf python3.11 -m venv /opt/swiftpdf/.venv
```

### Install Application

```bash
cd /opt/swiftpdf
sudo -u swiftpdf ./.venv/bin/pip install --upgrade pip setuptools wheel
sudo -u swiftpdf ./.venv/bin/pip install -e .
```

### Setup Directories

```bash
sudo mkdir -p /opt/swiftpdf/logs
sudo mkdir -p /var/tmp/swiftpdf
sudo chown swiftpdf:swiftpdf /opt/swiftpdf/logs
sudo chown swiftpdf:swiftpdf /var/tmp/swiftpdf
sudo chmod 750 /opt/swiftpdf/logs
sudo chmod 750 /var/tmp/swiftpdf
```

### Create Configuration

Create `/opt/swiftpdf/.env`:

```bash
FLASK_ENV=production
SWIFTPDF_SECRET_KEY=<generate-with-python-secrets-token>
MAX_CONTENT_LENGTH=104857600
TEMP_DIR=/var/tmp/swiftpdf
LOG_LEVEL=INFO
DATABASE_PATH=/opt/swiftpdf/instance/swiftpdf.sqlite3
```

Generate secret key:
```bash
python3 -c "import secrets; print('SWIFTPDF_SECRET_KEY=' + secrets.token_hex(32))"
```

## Step 3: Systemd Service

Create `/etc/systemd/system/swiftpdf.service`:

```ini
[Unit]
Description=SwiftPDF Web Service
After=network.target

[Service]
Type=simple
User=swiftpdf
WorkingDirectory=/opt/swiftpdf
Environment="PYTHONUNBUFFERED=1"
Environment="PATH=/opt/swiftpdf/.venv/bin"
EnvironmentFile=/opt/swiftpdf/.env
ExecStart=/opt/swiftpdf/.venv/bin/swiftpdf-ui --host 127.0.0.1 --port 5000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable swiftpdf
sudo systemctl start swiftpdf
```

Verify:
```bash
sudo systemctl status swiftpdf
```

## Step 4: Nginx Configuration

Create `/etc/nginx/sites-available/swiftpdf`:

```nginx
upstream swiftpdf {
    server 127.0.0.1:5000;
    keepalive 32;
}

server {
    listen 80;
    listen [::]:80;
    server_name pdf.example.com;

    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name pdf.example.com;

    # SSL Configuration (see SSL setup section below)
    ssl_certificate /etc/letsencrypt/live/pdf.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pdf.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # File Upload Limit
    client_max_body_size 100M;
    
    # Timeouts for large file processing
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    # Logging
    access_log /var/log/nginx/swiftpdf_access.log combined;
    error_log /var/log/nginx/swiftpdf_error.log;

    # Proxy Settings
    location / {
        proxy_pass http://swiftpdf;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_cache_bypass $http_upgrade;
    }

    # Static Files (if needed)
    location /static/ {
        alias /opt/swiftpdf/src/SwiftPDF/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/swiftpdf /etc/nginx/sites-enabled/
sudo nginx -t  # Test configuration
sudo systemctl restart nginx
```

## Step 5: SSL/TLS Certificate

### Using Let's Encrypt (Recommended)

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot certonly --nginx -d pdf.example.com
```

### Auto-Renewal

```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

## Step 6: Firewall Setup

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

## Step 7: Monitoring & Logging

### Setup Log Rotation

Create `/etc/logrotate.d/swiftpdf`:

```
/opt/swiftpdf/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 swiftpdf swiftpdf
    sharedscripts
    postrotate
        systemctl reload swiftpdf > /dev/null 2>&1 || true
    endscript
}
```

### Monitor Service

```bash
# Check service status
sudo systemctl status swiftpdf

# View logs
sudo journalctl -u swiftpdf -f

# View Nginx logs
sudo tail -f /var/log/nginx/swiftpdf_access.log
```

## Step 8: Database Backup

Create `/opt/swiftpdf/backup.sh`:

```bash
#!/bin/bash

BACKUP_DIR="/opt/swiftpdf/backups"
DB_PATH="/opt/swiftpdf/instance/swiftpdf.sqlite3"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
cp $DB_PATH $BACKUP_DIR/swiftpdf_$DATE.sqlite3

# Compress
gzip $BACKUP_DIR/swiftpdf_$DATE.sqlite3

# Keep only last 7 days
find $BACKUP_DIR -name "*.sqlite3.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR/swiftpdf_$DATE.sqlite3.gz"
```

Make executable:
```bash
sudo chmod +x /opt/swiftpdf/backup.sh
sudo chown swiftpdf:swiftpdf /opt/swiftpdf/backup.sh
```

Add to crontab:
```bash
sudo -u swiftpdf crontab -e
```

Add line:
```
0 2 * * * /opt/swiftpdf/backup.sh
```

## Performance Optimization

### Increase File Limits

Edit `/etc/security/limits.conf`:

```
swiftpdf soft nofile 65536
swiftpdf hard nofile 65536
```

### Nginx Worker Processes

Edit `/etc/nginx/nginx.conf`:

```nginx
worker_processes auto;
worker_connections 2048;
```

### System Tuning

```bash
# Increase system file descriptors
sudo echo "fs.file-max = 2097152" >> /etc/sysctl.conf
sudo sysctl -p
```

## Scaling (Optional)

### Using Gunicorn with Multiple Workers

Install Gunicorn:
```bash
sudo -u swiftpdf /opt/swiftpdf/.venv/bin/pip install gunicorn
```

Update systemd service ExecStart:
```
ExecStart=/opt/swiftpdf/.venv/bin/gunicorn \
  --workers 4 \
  --worker-class sync \
  --bind 127.0.0.1:5000 \
  --timeout 300 \
  SwiftPDF.web:create_app()
```

### Load Balancing

For multiple application servers, use Nginx upstream:

```nginx
upstream swiftpdf_cluster {
    server 127.0.0.1:5000;
    server 127.0.0.2:5000;
    server 127.0.0.3:5000;
    keepalive 32;
}
```

## Troubleshooting

### Service Won't Start

```bash
sudo journalctl -u swiftpdf -n 50
```

### Permission Denied

```bash
sudo chown -R swiftpdf:swiftpdf /opt/swiftpdf
sudo chmod 755 /opt/swiftpdf
```

### Disk Space Issues

```bash
# Check disk usage
df -h

# Clean temporary files
sudo rm -rf /var/tmp/swiftpdf/*

# Check database size
du -sh /opt/swiftpdf/instance/
```

### High Memory Usage

Monitor and adjust Nginx workers, or implement request queuing.

## Security Hardening

- [ ] Change SSH port
- [ ] Disable root SSH login
- [ ] Setup fail2ban
- [ ] Enable SELinux/AppArmor
- [ ] Regular security updates
- [ ] Configure firewall rules
- [ ] Setup intrusion detection
- [ ] Enable audit logging
- [ ] Regular security audits

## Monitoring & Alerting

Consider implementing:
- Health check endpoint
- Error rate monitoring
- Response time monitoring
- Disk space alerts
- Memory usage alerts
- CPU usage alerts

## Disaster Recovery Plan

1. Regular database backups (implemented above)
2. Version control for configuration
3. Document custom modifications
4. Test restore procedures
5. Keep recovery documentation
6. Practice failover procedures

## Maintenance Tasks

### Weekly
- Check service status
- Review error logs
- Verify backups

### Monthly
- Update system packages
- Review performance metrics
- Check SSL certificate expiration
- Test backup restore

### Quarterly
- Security audit
- Performance optimization review
- Load testing
- Disaster recovery drill

## Support & Documentation

For additional help:
- Check application logs: `sudo journalctl -u swiftpdf`
- Review Nginx logs: `/var/log/nginx/swiftpdf_*`
- Check system resources: `htop`, `df -h`
- Consult README.md for feature documentation
