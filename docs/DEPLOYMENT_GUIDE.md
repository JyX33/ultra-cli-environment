# Production Deployment Guide

This guide covers deploying the AI Reddit Agent with performance optimizations in production environments.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │───▶│   Reddit Agent  │───▶│   PostgreSQL    │
│   (nginx/HAProxy)│    │   (FastAPI)     │    │   Database      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                               │                         │
                       ┌───────▼───────┐        ┌───────▼───────┐
                       │     Redis     │        │   Monitoring  │
                       │    Cache      │        │  (Prometheus) │
                       └───────────────┘        └───────────────┘
```

## Prerequisites

### System Requirements

- **CPU**: 2+ cores (4+ recommended for production)
- **RAM**: 4GB minimum (8GB+ recommended)
- **Storage**: 20GB minimum (SSD recommended)
- **OS**: Ubuntu 20.04+ / CentOS 8+ / Docker environment

### Software Dependencies

- Python 3.12+
- PostgreSQL 13+
- Redis 6+
- nginx (for load balancing)
- Docker & Docker Compose (recommended)

## Quick Start with Docker

### 1. Clone and Configure

```bash
git clone <repository-url>
cd ai_reddit_agent

# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

### 2. Environment Configuration

```bash
# .env
# Reddit API Credentials
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=ai_reddit_agent/1.0

# OpenAI API
OPENAI_API_KEY=your_openai_api_key

# Database
DATABASE_URL=postgresql://reddit_user:secure_password@postgres:5432/reddit_agent

# Cache
ENABLE_REDIS=true
REDIS_URL=redis://redis:6379/0

# Performance
ENABLE_PERFORMANCE_MONITORING=true
MONITORING_INTERVAL_SECONDS=10

# Security
SECRET_KEY=your_secret_key_here
DEBUG=false
```

### 3. Deploy with Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  reddit-agent:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://reddit_user:${POSTGRES_PASSWORD}@postgres:5432/reddit_agent
      - REDIS_URL=redis://redis:6379/0
      - ENABLE_REDIS=true
      - ENABLE_PERFORMANCE_MONITORING=true
    env_file:
      - .env
    depends_on:
      - postgres
      - redis
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=reddit_agent
      - POSTGRES_USER=reddit_user
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init-db.sql
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U reddit_user"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - reddit-agent
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### 4. Start Services

```bash
# Build and start all services
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f reddit-agent
```

## Manual Installation

### 1. System Setup

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib redis-server nginx

# CentOS/RHEL
sudo dnf install -y python3.12 python3-pip postgresql postgresql-server redis nginx
```

### 2. Database Setup

```bash
# PostgreSQL setup
sudo -u postgres createuser --createdb reddit_user
sudo -u postgres createdb reddit_agent -O reddit_user
sudo -u postgres psql -c "ALTER USER reddit_user PASSWORD 'secure_password';"

# Redis setup
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

### 3. Application Setup

```bash
# Create application user
sudo useradd -m -s /bin/bash reddit-agent
sudo su - reddit-agent

# Clone repository
git clone <repository-url>
cd ai_reddit_agent

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies with performance features
pip install -e ".[performance]"

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Run database migrations
alembic upgrade head

# Test installation
python -m app.main_optimized
```

### 4. Systemd Service

```ini
# /etc/systemd/system/reddit-agent.service
[Unit]
Description=AI Reddit Agent
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
Type=exec
User=reddit-agent
Group=reddit-agent
WorkingDirectory=/home/reddit-agent/ai_reddit_agent
Environment=PATH=/home/reddit-agent/ai_reddit_agent/.venv/bin
EnvironmentFile=/home/reddit-agent/ai_reddit_agent/.env
ExecStart=/home/reddit-agent/ai_reddit_agent/.venv/bin/python -m uvicorn app.main_optimized:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

# Performance and security
LimitNOFILE=65536
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/home/reddit-agent/ai_reddit_agent/logs
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable reddit-agent
sudo systemctl start reddit-agent
sudo systemctl status reddit-agent
```

## Load Balancer Configuration

### nginx Configuration

```nginx
# /etc/nginx/sites-available/reddit-agent
upstream reddit_agent {
    # Multiple instances for load balancing
    server 127.0.0.1:8000 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8001 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8002 max_fails=3 fail_timeout=30s;
}

# Rate limiting
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL Configuration
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubdomains" always;
    
    # Rate limiting
    limit_req zone=api burst=20 nodelay;
    
    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml;
    
    # Performance optimizations
    client_max_body_size 10M;
    client_body_timeout 30s;
    client_header_timeout 30s;
    keepalive_timeout 30s;
    
    location / {
        proxy_pass http://reddit_agent;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        proxy_pass http://reddit_agent;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
    
    # Performance monitoring (restrict access)
    location /performance/ {
        # Restrict to internal IPs
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        deny all;
        
        proxy_pass http://reddit_agent;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

## Monitoring and Logging

### Application Logging

```python
# logging_config.py
import logging.config

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
        'json': {
            'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
        }
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard'
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/reddit_agent.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'json'
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/reddit_agent_errors.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'json'
        }
    },
    'loggers': {
        '': {  # Root logger
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False
        },
        'app': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'DEBUG',
            'propagate': False
        }
    }
}

logging.config.dictConfig(LOGGING_CONFIG)
```

### Prometheus Metrics

```python
# metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import FastAPI, Response

# Define metrics
REQUEST_COUNT = Counter('requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration')
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active connections')
CACHE_HIT_RATE = Gauge('cache_hit_rate', 'Cache hit rate')
DATABASE_QUERY_COUNT = Counter('database_queries_total', 'Total database queries')

def setup_metrics(app: FastAPI):
    @app.middleware("http")
    async def metrics_middleware(request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        
        REQUEST_DURATION.observe(duration)
        
        return response
    
    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type="text/plain")
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "AI Reddit Agent Performance",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(request_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile"
          }
        ]
      },
      {
        "title": "Cache Hit Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "cache_hit_rate",
            "legendFormat": "Hit Rate"
          }
        ]
      }
    ]
  }
}
```

## Security Configuration

### Environment Security

```bash
# Secure environment variables
echo 'export REDDIT_CLIENT_SECRET="$(cat /etc/reddit-agent/reddit_secret)"' >> /etc/profile.d/reddit-agent.sh
echo 'export OPENAI_API_KEY="$(cat /etc/reddit-agent/openai_key)"' >> /etc/profile.d/reddit-agent.sh
echo 'export SECRET_KEY="$(cat /etc/reddit-agent/secret_key)"' >> /etc/profile.d/reddit-agent.sh

# Set proper permissions
chmod 600 /etc/reddit-agent/*
chown reddit-agent:reddit-agent /etc/reddit-agent/*
```

### Database Security

```sql
-- Create dedicated database user
CREATE USER reddit_app WITH PASSWORD 'secure_app_password';

-- Grant minimal required permissions
GRANT CONNECT ON DATABASE reddit_agent TO reddit_app;
GRANT USAGE ON SCHEMA public TO reddit_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO reddit_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO reddit_app;

-- Enable row-level security (if needed)
ALTER TABLE reddit_posts ENABLE ROW LEVEL SECURITY;
```

### API Security

```python
# rate_limiting.py
from fastapi import HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# Apply rate limiting
@app.get("/check-updates/{subreddit}/{topic}")
@limiter.limit("10/minute")
async def check_updates(request: Request, subreddit: str, topic: str):
    # Implementation
    pass

# Custom rate limit handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

## Backup and Recovery

### Database Backup

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/var/backups/reddit-agent"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="reddit_agent"
DB_USER="reddit_user"

# Create backup directory
mkdir -p $BACKUP_DIR

# Database backup
pg_dump -h localhost -U $DB_USER -W $DB_NAME | gzip > "$BACKUP_DIR/db_backup_$DATE.sql.gz"

# Keep only last 7 days of backups
find $BACKUP_DIR -name "db_backup_*.sql.gz" -mtime +7 -delete

# Upload to S3 (optional)
# aws s3 cp "$BACKUP_DIR/db_backup_$DATE.sql.gz" s3://your-backup-bucket/reddit-agent/
```

### Automated Backup

```bash
# Add to crontab
crontab -e

# Daily backup at 2 AM
0 2 * * * /usr/local/bin/backup.sh >> /var/log/reddit-agent-backup.log 2>&1
```

### Recovery Procedures

```bash
# Restore from backup
gunzip -c /var/backups/reddit-agent/db_backup_20250617_020000.sql.gz | psql -h localhost -U reddit_user reddit_agent

# Restore Redis data
redis-cli --rdb /var/backups/redis/dump.rdb

# Application recovery
systemctl stop reddit-agent
# Restore application files if needed
systemctl start reddit-agent
```

## Scaling and High Availability

### Horizontal Scaling

```yaml
# docker-compose.scale.yml
version: '3.8'

services:
  reddit-agent:
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 512M
          cpus: '0.25'
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
```

### Database Replication

```yaml
# PostgreSQL master-slave setup
postgres-master:
  image: postgres:15-alpine
  environment:
    - POSTGRES_REPLICATION_MODE=master
    - POSTGRES_REPLICATION_USER=replicator
    - POSTGRES_REPLICATION_PASSWORD=repl_password

postgres-slave:
  image: postgres:15-alpine
  environment:
    - POSTGRES_REPLICATION_MODE=slave
    - POSTGRES_REPLICATION_USER=replicator
    - POSTGRES_REPLICATION_PASSWORD=repl_password
    - POSTGRES_MASTER_SERVICE=postgres-master
```

### Redis Clustering

```yaml
redis-cluster:
  image: redis:7-alpine
  command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf
  deploy:
    replicas: 6
```

## Performance Tuning

### Database Optimization

```sql
-- PostgreSQL performance tuning
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;

-- Reload configuration
SELECT pg_reload_conf();
```

### Application Tuning

```python
# uvicorn_config.py
UVICORN_CONFIG = {
    "host": "0.0.0.0",
    "port": 8000,
    "workers": 4,  # CPU cores * 2
    "worker_class": "uvicorn.workers.UvicornWorker",
    "worker_connections": 1000,
    "max_requests": 10000,
    "max_requests_jitter": 1000,
    "timeout": 30,
    "keepalive": 2,
    "preload_app": True,
}
```

## Troubleshooting

### Common Issues

1. **High Memory Usage**
   ```bash
   # Check memory usage
   docker stats
   
   # Analyze memory leaks
   docker exec -it reddit-agent python -c "
   import psutil
   process = psutil.Process()
   print(f'Memory: {process.memory_info().rss / 1024 / 1024:.1f} MB')
   "
   ```

2. **Database Connection Issues**
   ```bash
   # Check connections
   sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"
   
   # Kill long-running queries
   sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'active' AND query_start < now() - interval '5 minutes';"
   ```

3. **Redis Connection Issues**
   ```bash
   # Check Redis status
   redis-cli ping
   
   # Monitor Redis
   redis-cli monitor
   
   # Check memory usage
   redis-cli info memory
   ```

### Log Analysis

```bash
# Monitor application logs
tail -f /app/logs/reddit_agent.log | grep ERROR

# Analyze performance
grep "Response time" /app/logs/reddit_agent.log | awk '{print $NF}' | sort -n

# Check for memory issues
grep "Memory" /app/logs/reddit_agent.log | tail -20
```

### Health Checks

```bash
#!/bin/bash
# health_check.sh

# Check API health
curl -f http://localhost:8000/ || exit 1

# Check database
pg_isready -h localhost -U reddit_user || exit 1

# Check Redis
redis-cli ping | grep PONG || exit 1

# Check performance metrics
RESPONSE_TIME=$(curl -s -o /dev/null -w "%{time_total}" http://localhost:8000/performance/stats)
if (( $(echo "$RESPONSE_TIME > 2.0" | bc -l) )); then
    echo "High response time: $RESPONSE_TIME"
    exit 1
fi

echo "Health check passed"
```

## Migration from Development

### Data Migration

```bash
# Export development data
pg_dump -h localhost -U dev_user dev_reddit_agent > dev_export.sql

# Import to production (after sanitization)
psql -h prod-host -U reddit_user reddit_agent < prod_import.sql
```

### Configuration Migration

```bash
# Update configuration for production
sed -i 's/DEBUG=true/DEBUG=false/' .env
sed -i 's/localhost/prod-host/' .env

# Update database URLs
sed -i 's/sqlite:\/\//postgresql:\/\//' .env
```

### Zero-Downtime Deployment

```bash
# Blue-green deployment script
#!/bin/bash

# Build new version
docker build -t reddit-agent:blue .

# Start blue environment
docker-compose -f docker-compose.blue.yml up -d

# Health check
./health_check.sh blue

# Switch traffic
nginx -s reload  # Update nginx config

# Stop green environment
docker-compose -f docker-compose.green.yml down
```

This deployment guide provides comprehensive instructions for production deployment with performance optimizations, monitoring, and high availability configurations.