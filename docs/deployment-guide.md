# ConsentOS Deployment Guide

This guide covers deploying ConsentOS in production across three environments:

1. [Docker Compose](#1-docker-compose) — single VM, the quickest path to production
2. [Kubernetes (Helm)](#2-kubernetes-helm) — multi-node, auto-scaling, the long-term path
3. [Cloud Run / Serverless](#3-cloud-run--serverless) — managed containers, minimal ops

All three share the same container images, environment variables, and bootstrap flow. Pick whichever matches your infrastructure; mix and match where it makes sense (e.g. Cloud SQL for the database, Cloud Run for the API).

---

## Prerequisites

Before you begin, you'll need:

| Item | Notes |
|------|-------|
| **Domain name** | Two DNS records: one for the admin UI + banner CDN (e.g. `cmp.example.com`), one for each customer site that embeds the banner (their own domains). |
| **TLS certificates** | Terminate TLS at your reverse proxy / load balancer (Caddy, nginx, Cloud Load Balancer). The containers serve plain HTTP internally. |
| **PostgreSQL 16+** | Built-in via Docker / Helm, or managed (RDS, Cloud SQL, Supabase). |
| **Redis 7+** | Built-in or managed (ElastiCache, Memorystore, Upstash). |
| **Docker or container runtime** | Docker Engine 24+ with Compose v2, or a Kubernetes cluster with Helm 3. |
| **Git** | To clone the repository. |

### Generating secrets

Several environment variables require strong random values. Generate them with:

```bash
# JWT secret — used to sign access and refresh tokens
openssl rand -hex 32

# Postgres password
openssl rand -hex 24

# Redis password
openssl rand -hex 24

# Admin bootstrap token (optional — gates runtime org creation)
openssl rand -hex 32
```

---

## Environment Variables Reference

All ConsentOS services read configuration from environment variables (or a `.env` file in Docker Compose). The canonical list with defaults is in `.env.example` at the repository root. The critical ones for production are:

### Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENVIRONMENT` | Yes | `development` | Set to `production`. The API refuses to start with unsafe defaults (placeholder JWT secret, wildcard CORS) when this is not `development`/`dev`/`test`. |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

### Database & Redis

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://consentos:consentos@postgres:5432/consentos` | Async SQLAlchemy connection string. |
| `POSTGRES_USER` | Docker only | — | Used by the Postgres container to initialise the database. |
| `POSTGRES_PASSWORD` | Docker only | — | See above. |
| `POSTGRES_DB` | Docker only | — | See above. |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Include the password as `redis://default:<password>@host:6379/0` if auth is enabled. |
| `REDIS_PASSWORD` | Docker only | — | Passed to the Redis container's `--requirepass`. |

### Authentication & Security

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET_KEY` | Yes | `CHANGE-ME-in-production` | Must be replaced. The API refuses to start in production with the placeholder value. Generate with `openssl rand -hex 32`. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | Access token lifetime. |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifetime. |
| `ALLOWED_ORIGINS` | Yes | `http://localhost:5173` | Comma-separated list of origins allowed to call the API. Include the admin UI origin and every customer site that embeds the banner. Wildcards are refused when `ENVIRONMENT` is not dev/test. |

### Initial Admin Bootstrap

On first startup, if the `users` table is empty and both credentials below are set, the bootstrap init container creates an organisation and an owner user so you can log in to the admin UI. Idempotent — once any user exists, this is a no-op.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `INITIAL_ADMIN_EMAIL` | Recommended | — | E-mail address for the first admin user. |
| `INITIAL_ADMIN_PASSWORD` | Recommended | — | Password for the first admin user. **Rotate via the admin UI after first login.** |
| `INITIAL_ADMIN_FULL_NAME` | No | `Administrator` | Display name. |
| `INITIAL_ORG_NAME` | No | `Default Organisation` | Name of the initial organisation. |
| `INITIAL_ORG_SLUG` | No | `default` | URL slug for the initial organisation. |

### CDN & Banner

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CDN_BASE_URL` | Yes | `http://localhost:5173` | Public URL where `consent-loader.js` and `consent-bundle.js` are hosted. In the default Docker Compose deployment, this is the same origin as the admin UI (the admin-ui image bundles the banner at its nginx root). |

### GeoIP

ConsentOS resolves visitor location for regional consent modes (e.g. opt-in for EU, opt-out for California). Resolution runs in order: CDN headers → local MaxMind database → external API fallback.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEOIP_COUNTRY_HEADER` | No | — | Custom HTTP header carrying the visitor's ISO 3166-1 alpha-2 country code. Checked before the built-in list (`cf-ipcountry`, `x-vercel-ip-country`, `x-appengine-country`, `x-country-code`). Case-insensitive. |
| `GEOIP_REGION_HEADER` | No | — | Companion header carrying the ISO 3166-2 subdivision code (e.g. `CA` for California, `SCT` for Scotland). Paired with `GEOIP_COUNTRY_HEADER` to produce region keys like `US-CA` or `GB-SCT`. |
| `GEOIP_MAXMIND_DB_PATH` | No | — | Path to a local MaxMind GeoLite2-City `.mmdb` file. Used when no CDN header resolves. Download from [MaxMind](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) (free, registration required). |

**Common CDN header configurations:**

| CDN / Load Balancer | `GEOIP_COUNTRY_HEADER` | `GEOIP_REGION_HEADER` |
|---------------------|------------------------|-----------------------|
| Cloudflare (all plans) | `cf-ipcountry` *(built-in, no env needed)* | — |
| Cloudflare (Enterprise) | `cf-ipcountry` *(built-in)* | `cf-region-code` |
| Vercel | `x-vercel-ip-country` *(built-in)* | `x-vercel-ip-country-region` |
| Google Cloud Load Balancer | `x-gclb-country` | `x-gclb-region` |
| AWS CloudFront (functions) | `cloudfront-viewer-country` | `cloudfront-viewer-country-region` |
| Generic / custom | *your header name* | *your header name* |

> **Cloudflare users**: `cf-ipcountry` is in the built-in list, so you don't need to set `GEOIP_COUNTRY_HEADER` at all. Country-level resolution works out of the box. For US-state or UK-region granularity, set `GEOIP_REGION_HEADER=cf-region-code` (requires a Cloudflare Enterprise plan or a Managed Transform rule that exposes the header).

### Scanner

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SCANNER_SERVICE_URL` | Yes (API) | `http://localhost:8001` | URL the Celery worker uses to reach the scanner service. In Docker Compose this is `http://consentos-scanner:8001`. |

> **Important**: the scanner must NOT share the API's `.env` file via `env_file:`. Variables like `PORT` leak across and rebind the scanner off its default `8001`. Use an explicit `environment:` block instead (the prod compose already does this).

---

## 1. Docker Compose

The fastest path to a running ConsentOS instance. One VM, one `docker compose up`, everything behind a reverse proxy like Caddy or nginx.

### 1.1 Clone the repository

```bash
git clone https://github.com/ConsentOS/consentos.git /opt/consentos
cd /opt/consentos
```

### 1.2 Create the `.env` file

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
ENVIRONMENT=production

# Database
DATABASE_URL=postgresql+asyncpg://consentos:<POSTGRES_PASSWORD>@postgres:5432/consentos
POSTGRES_USER=consentos
POSTGRES_PASSWORD=<generate with openssl rand -hex 24>
POSTGRES_DB=consentos

# Redis
REDIS_URL=redis://default:<REDIS_PASSWORD>@redis:6379/0
REDIS_PASSWORD=<generate with openssl rand -hex 24>

# JWT
JWT_SECRET_KEY=<generate with openssl rand -hex 32>

# CDN — same origin as the admin UI in this setup
CDN_BASE_URL=https://cmp.example.com

# CORS — admin origin + every customer site embedding the banner
ALLOWED_ORIGINS=https://cmp.example.com,https://www.example.com

# Initial admin
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_PASSWORD=<strong temporary password>

# GeoIP — if behind Cloudflare, country detection works automatically.
# For state/region granularity behind Cloudflare Enterprise:
# GEOIP_REGION_HEADER=cf-region-code
```

### 1.3 Start the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The init container (`consentos-bootstrap`) runs Alembic migrations and creates the initial admin user, then exits. All other services wait for it via `service_completed_successfully`.

### 1.4 Verify

```bash
# Check services
docker compose -f docker-compose.prod.yml ps

# API health
curl http://localhost:11001/health

# Deep readiness (checks Postgres + Redis)
curl http://localhost:11001/health/ready
```

### 1.5 Reverse proxy

The API listens on `127.0.0.1:11001` and the admin UI on `127.0.0.1:11002`. Put a reverse proxy in front to terminate TLS.

**Caddy example** (`/etc/caddy/Caddyfile`):

```caddyfile
cmp.example.com {
    # API
    handle /api/v1/* {
        reverse_proxy localhost:11001
    }

    # Hosted policy pages
    handle /c/* {
        reverse_proxy localhost:11001
    }

    # Health check
    handle /health {
        reverse_proxy localhost:11001
    }

    # Admin UI + banner CDN (catch-all, must be last)
    reverse_proxy localhost:11002
}
```

Caddy handles TLS automatically via Let's Encrypt. Reload after creating the file:

```bash
sudo systemctl reload caddy
```

**nginx example** (`/etc/nginx/sites-enabled/consentos`):

```nginx
server {
    listen 443 ssl http2;
    server_name cmp.example.com;

    ssl_certificate     /etc/letsencrypt/live/cmp.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cmp.example.com/privkey.pem;

    location /api/v1/ {
        proxy_pass http://127.0.0.1:11001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /c/ {
        proxy_pass http://127.0.0.1:11001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:11001;
    }

    location / {
        proxy_pass http://127.0.0.1:11002;
    }
}
```

### 1.6 Integrate the banner

Add the loader to every page on your customer site, **as the very first `<script>` in `<head>`** — no `async`, no `defer`:

```html
<script src="https://cmp.example.com/consent-loader.js"
        data-site-id="<site-id-from-admin-ui>"
        data-api-base="https://cmp.example.com"></script>
```

> **Critical**: the loader must run synchronously before any other script. If another script executes first (e.g. Google Tag Manager), it can set cookies before the blocker is installed. The loader will sweep classified pre-existing cookies on load, but `Set-Cookie` response headers from network requests cannot be intercepted from JavaScript — only blocking the source script prevents those.

### 1.7 Updating

```bash
cd /opt/consentos
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker image prune -f
```

The bootstrap init container runs migrations automatically on every start, so schema updates are applied without manual intervention.

---

## 2. Kubernetes (Helm)

For multi-node deployments with auto-scaling, rolling updates, and integration with managed databases and Redis.

### 2.1 Prerequisites

- A Kubernetes cluster (1.24+)
- Helm 3
- Container images pushed to a registry (GHCR, ECR, GCR, etc.)
- A managed PostgreSQL instance (recommended) or an in-cluster one
- A managed Redis instance (recommended) or an in-cluster one

### 2.2 Build and push images

```bash
# API + Celery worker/beat (same image, different entrypoint)
docker build -t ghcr.io/consentos/consentos-api:latest apps/api/
docker push ghcr.io/consentos/consentos-api:latest

# Scanner
docker build -t ghcr.io/consentos/consentos-scanner:latest apps/scanner/
docker push ghcr.io/consentos/consentos-scanner:latest

# Admin UI + banner (build context = repo root)
docker build -f apps/admin-ui/Dockerfile -t ghcr.io/consentos/consentos-admin-ui:latest .
docker push ghcr.io/consentos/consentos-admin-ui:latest
```

### 2.3 Create a values override

```yaml
# values.prod.yaml

api:
  replicaCount: 3
  env:
    ENVIRONMENT: production
    LOG_LEVEL: INFO
    ALLOWED_ORIGINS: "https://cmp.example.com,https://www.example.com"
    CDN_BASE_URL: "https://cmp.example.com"
    SCANNER_SERVICE_URL: "http://consentos-scanner:8001"
    # GeoIP — behind Cloudflare, country resolves automatically.
    # For state-level behind Cloudflare Enterprise:
    # GEOIP_REGION_HEADER: cf-region-code
    # Or mount a MaxMind DB and set:
    # GEOIP_MAXMIND_DB_PATH: /data/GeoLite2-City.mmdb

scanner:
  replicaCount: 1
  resources:
    limits:
      memory: 1Gi

adminUi:
  replicaCount: 2

# Use managed Postgres (e.g. Cloud SQL, RDS)
postgresql:
  enabled: false
  externalUrl: "postgresql+asyncpg://consentos:<PASSWORD>@<HOST>:5432/consentos"

# Use managed Redis (e.g. Memorystore, ElastiCache)
redis:
  enabled: false
  externalUrl: "redis://default:<PASSWORD>@<HOST>:6379/0"

# Ingress (nginx-ingress or similar)
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: cmp.example.com
      paths:
        - path: /api
          pathType: Prefix
          service: api
        - path: /c
          pathType: Prefix
          service: api
        - path: /health
          pathType: Prefix
          service: api
        - path: /
          pathType: Prefix
          service: admin-ui
  tls:
    - secretName: consentos-tls
      hosts:
        - cmp.example.com

# Secrets
secrets:
  jwtSecretKey: "<generate with openssl rand -hex 32>"
  postgresqlPassword: "<your managed DB password>"
```

### 2.4 Install the chart

```bash
helm install consentos helm/consentos/ \
  -f values.prod.yaml \
  --namespace consentos \
  --create-namespace
```

### 2.5 Run the bootstrap

The Helm chart doesn't include an init container by default. Run the bootstrap as a one-off Kubernetes Job:

```bash
kubectl run consentos-bootstrap \
  --namespace consentos \
  --image ghcr.io/consentos/consentos-api:latest \
  --restart=Never \
  --env="DATABASE_URL=postgresql+asyncpg://consentos:<PW>@<HOST>:5432/consentos" \
  --env="INITIAL_ADMIN_EMAIL=admin@example.com" \
  --env="INITIAL_ADMIN_PASSWORD=<temporary password>" \
  --env="JWT_SECRET_KEY=<your key>" \
  --env="ENVIRONMENT=production" \
  --command -- sh -c "python -m alembic upgrade head && python -m src.cli.bootstrap_admin"
```

Wait for it to complete, then delete the pod:

```bash
kubectl wait --for=condition=Ready pod/consentos-bootstrap -n consentos --timeout=120s
kubectl delete pod consentos-bootstrap -n consentos
```

### 2.6 Verify

```bash
kubectl get pods -n consentos
curl https://cmp.example.com/health/ready
```

### 2.7 Updating

```bash
# Rebuild and push images with a new tag
docker build -t ghcr.io/consentos/consentos-api:v1.2.0 apps/api/
docker push ghcr.io/consentos/consentos-api:v1.2.0

# Upgrade the Helm release
helm upgrade consentos helm/consentos/ \
  -f values.prod.yaml \
  --set api.image.tag=v1.2.0 \
  --set scanner.image.tag=v1.2.0 \
  --set adminUi.image.tag=v1.2.0 \
  --namespace consentos
```

Helm performs a rolling update. The API Dockerfile runs migrations on startup (the Dockerfile's `CMD` includes `alembic upgrade head`), so schema updates are applied automatically as new pods come up.

> **Note**: In the Docker Compose deployment, migrations are owned by the init container, and the API's `CMD` only runs `uvicorn`. In Kubernetes, since there's no native "init container completes first" guarantee across separate Deployments, each API pod runs its own `alembic upgrade head` on startup. Alembic migrations are idempotent, so multiple pods running them concurrently is safe.

### 2.8 GeoIP with MaxMind on Kubernetes

If you need local MaxMind lookups (e.g. behind a load balancer that doesn't inject GeoIP headers), mount the database file via a PersistentVolumeClaim or a ConfigMap:

```yaml
# In values.prod.yaml
api:
  env:
    GEOIP_MAXMIND_DB_PATH: /data/GeoLite2-City.mmdb
  extraVolumes:
    - name: geoip-db
      persistentVolumeClaim:
        claimName: geoip-db
  extraVolumeMounts:
    - name: geoip-db
      mountPath: /data
      readOnly: true
```

Use a CronJob to refresh the MaxMind database weekly:

```bash
kubectl create cronjob geoip-update \
  --namespace consentos \
  --schedule="0 3 * * 0" \
  --image maxmindinc/geoipupdate \
  --env="GEOIPUPDATE_ACCOUNT_ID=<your-id>" \
  --env="GEOIPUPDATE_LICENSE_KEY=<your-key>" \
  --env="GEOIPUPDATE_EDITION_IDS=GeoLite2-City"
```

---

## 3. Cloud Run / Serverless

For teams that want managed scaling, zero cold-infrastructure, and pay-per-request pricing. This guide uses Google Cloud Run as the reference, but the pattern adapts to AWS App Runner, Azure Container Apps, or Fly.io.

### 3.1 Architecture

| Component | Service | Notes |
|-----------|---------|-------|
| API | Cloud Run service | Scales to zero. Connects to Cloud SQL + Memorystore. |
| Admin UI + banner | Cloud Run service (or Cloud Storage + CDN) | Static files — can also be served from a GCS bucket behind Cloud CDN. |
| Celery worker | Cloud Run Job or always-on instance (min 1) | Must be always-on to process the Redis queue. Cloud Run Jobs work for batch processing but not for long-polling Celery workers — use an always-on revision with `--min-instances=1`. |
| Celery beat | Cloud Run Job (scheduled) or Cloud Scheduler + Pub/Sub | Triggers periodic tasks. Alternatively, use Cloud Scheduler to invoke the API's scan endpoints directly. |
| Scanner | Cloud Run service (or separate VM) | Needs 1 GB+ RAM and `/dev/shm` > 64 MB for Playwright/Chromium. Cloud Run supports custom `/dev/shm` sizes via `--execution-environment=gen2`. |
| PostgreSQL | Cloud SQL | Managed, auto-backups, replicas. |
| Redis | Memorystore for Redis | Or Upstash for a serverless Redis. |

### 3.2 Build and push images

```bash
# Tag for Artifact Registry (or Container Registry)
export REGION=europe-west1
export PROJECT=my-gcp-project
export REGISTRY=${REGION}-docker.pkg.dev/${PROJECT}/consentos

docker build -t ${REGISTRY}/api:latest apps/api/
docker build -t ${REGISTRY}/scanner:latest apps/scanner/
docker build -f apps/admin-ui/Dockerfile -t ${REGISTRY}/admin-ui:latest .

docker push ${REGISTRY}/api:latest
docker push ${REGISTRY}/scanner:latest
docker push ${REGISTRY}/admin-ui:latest
```

### 3.3 Provision managed infrastructure

```bash
# Cloud SQL (Postgres 16)
gcloud sql instances create consentos-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=${REGION} \
  --root-password=<POSTGRES_PASSWORD>

gcloud sql databases create consentos --instance=consentos-db
gcloud sql users create consentos --instance=consentos-db --password=<POSTGRES_PASSWORD>

# Memorystore (Redis 7)
gcloud redis instances create consentos-redis \
  --size=1 \
  --region=${REGION} \
  --redis-version=redis_7_0
```

### 3.4 Deploy the API

```bash
gcloud run deploy consentos-api \
  --image ${REGISTRY}/api:latest \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --min-instances=1 \
  --max-instances=10 \
  --memory=512Mi \
  --cpu=1 \
  --port=8000 \
  --set-env-vars="ENVIRONMENT=production" \
  --set-env-vars="DATABASE_URL=postgresql+asyncpg://consentos:<PW>@<CLOUD_SQL_IP>:5432/consentos" \
  --set-env-vars="REDIS_URL=redis://<MEMORYSTORE_IP>:6379/0" \
  --set-env-vars="JWT_SECRET_KEY=<your-key>" \
  --set-env-vars="CDN_BASE_URL=https://cmp.example.com" \
  --set-env-vars="ALLOWED_ORIGINS=https://cmp.example.com,https://www.example.com" \
  --set-env-vars="SCANNER_SERVICE_URL=https://consentos-scanner-<hash>.run.app" \
  --set-env-vars="INITIAL_ADMIN_EMAIL=admin@example.com" \
  --set-env-vars="INITIAL_ADMIN_PASSWORD=<temp-pw>" \
  --add-cloudsql-instances=${PROJECT}:${REGION}:consentos-db \
  --vpc-connector=consentos-vpc-connector
```

> **Tip**: Use Secret Manager for sensitive values instead of inline `--set-env-vars`:
> ```bash
> --set-secrets="JWT_SECRET_KEY=jwt-secret:latest,POSTGRES_PASSWORD=pg-password:latest"
> ```

### 3.5 Deploy the admin UI

```bash
gcloud run deploy consentos-admin \
  --image ${REGISTRY}/admin-ui:latest \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=5 \
  --memory=128Mi \
  --cpu=1 \
  --port=80
```

### 3.6 Deploy the scanner

The scanner needs generous memory and `/dev/shm` for Playwright:

```bash
gcloud run deploy consentos-scanner \
  --image ${REGISTRY}/scanner:latest \
  --region ${REGION} \
  --platform managed \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=3 \
  --memory=1Gi \
  --cpu=2 \
  --port=8001 \
  --execution-environment=gen2 \
  --set-env-vars="CRAWLER_HEADLESS=true,LOG_LEVEL=INFO"
```

### 3.7 Deploy the Celery worker

Cloud Run isn't ideal for long-running Celery workers (it expects request-driven traffic). Options:

**Option A — always-on Cloud Run revision:**

```bash
gcloud run deploy consentos-worker \
  --image ${REGISTRY}/api:latest \
  --region ${REGION} \
  --platform managed \
  --no-allow-unauthenticated \
  --min-instances=1 \
  --max-instances=3 \
  --memory=512Mi \
  --cpu=1 \
  --no-cpu-throttling \
  --command="celery","-A","src.celery_app","worker","--loglevel=info","--concurrency=2" \
  --set-env-vars="DATABASE_URL=...,REDIS_URL=...,SCANNER_SERVICE_URL=..." \
  --vpc-connector=consentos-vpc-connector
```

**Option B — Compute Engine (GCE) or a small GKE node** running just the Celery worker and beat. Simpler, cheaper for steady-state workloads.

### 3.8 Run the bootstrap

Run as a one-off Cloud Run Job:

```bash
gcloud run jobs create consentos-bootstrap \
  --image ${REGISTRY}/api:latest \
  --region ${REGION} \
  --command="sh","-c","python -m alembic upgrade head && python -m src.cli.bootstrap_admin" \
  --set-env-vars="DATABASE_URL=...,INITIAL_ADMIN_EMAIL=...,INITIAL_ADMIN_PASSWORD=...,JWT_SECRET_KEY=...,ENVIRONMENT=production" \
  --vpc-connector=consentos-vpc-connector

gcloud run jobs execute consentos-bootstrap --region ${REGION} --wait
```

### 3.9 Set up routing

Use a Google Cloud Load Balancer (or Cloudflare in front) to route:

| Path | Backend |
|------|---------|
| `/api/v1/*` | `consentos-api` Cloud Run service |
| `/c/*` | `consentos-api` Cloud Run service |
| `/health` | `consentos-api` Cloud Run service |
| `/*` (default) | `consentos-admin` Cloud Run service |

If using Cloudflare as the CDN and reverse proxy, `cf-ipcountry` is injected automatically — no `GEOIP_COUNTRY_HEADER` env var needed. For state-level granularity with Cloudflare Enterprise, set `GEOIP_REGION_HEADER=cf-region-code`.

If using Google Cloud Load Balancer directly (no Cloudflare), set:

```
GEOIP_COUNTRY_HEADER=x-gclb-country
GEOIP_REGION_HEADER=x-gclb-region
```

### 3.10 GeoIP considerations for serverless

Serverless platforms don't have a persistent filesystem for MaxMind databases. Your options:

1. **CDN headers** (recommended) — Cloudflare, Vercel, and GCP Load Balancer all inject country headers. Zero config beyond the env var.
2. **Mount from GCS** — Use a GCS FUSE volume mount to expose the `.mmdb` file:
   ```bash
   gcloud run deploy consentos-api \
     --add-volume=name=geoip,type=cloud-storage,bucket=my-geoip-bucket \
     --add-volume-mount=volume=geoip,mount-path=/data \
     --set-env-vars="GEOIP_MAXMIND_DB_PATH=/data/GeoLite2-City.mmdb"
   ```
3. **Bake into the image** — Copy the `.mmdb` into the Dockerfile. Simple but stale until you rebuild.

---

## Banner Integration Checklist

Regardless of deployment method, verify these before going live:

- [ ] `consent-loader.js` is the **very first `<script>` in `<head>`** on every customer page. No `async`. No `defer`.
- [ ] `data-site-id` and `data-api-base` attributes are set correctly on the script tag.
- [ ] The API's `ALLOWED_ORIGINS` includes every customer site origin that embeds the banner.
- [ ] `CDN_BASE_URL` points at the origin where `consent-loader.js` and `consent-bundle.js` are served (same as the admin UI in a standard deployment).
- [ ] Google Tag Manager (if used) is loaded **after** the ConsentOS loader, not before.
- [ ] The consent cookie (`_consentos_consent`) is accessible on the customer domain — check that `SameSite=Lax` and the domain/path are correct.
- [ ] Regional modes are configured in the admin UI for any site that needs location-aware consent (e.g. opt-in for EU, opt-out for US-CA).
- [ ] GeoIP headers are flowing from your CDN/load balancer — verify with `curl -I https://cmp.example.com/api/v1/config/sites/<id>` and check for `cf-ipcountry` or your custom header.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `_ga` cookie appears before consent | The ConsentOS loader isn't the first script on the page, or it's loaded with `async`/`defer`. | Move the loader to the very top of `<head>` and remove `async`/`defer`. |
| CORS error on banner config fetch | The customer site's origin isn't in `ALLOWED_ORIGINS`. | Add the origin to the comma-separated list and redeploy. |
| Scanner fails with `httpx.ConnectError` | `SCANNER_SERVICE_URL` doesn't match the scanner's actual address/port, or the scanner's port was overridden by a shared `PORT` env var. | Verify the URL and ensure the scanner uses a scoped `environment:` block, not `env_file: .env`. |
| API refuses to start: "unsafe configuration" | `JWT_SECRET_KEY` is the placeholder value, or `ALLOWED_ORIGINS` contains `*`, and `ENVIRONMENT` is set to `production`. | Set real values for both. |
| Cookies still blocked after accepting consent | The loader and banner bundle are separate IIFEs with independent module state. If `window.__consentos._updateBlocker` is missing, the bundle can't drive the loader's blocker. | Upgrade to the latest version — the bridge was added in the `fix/blocker-loader-bundle-bridge` PR. |
| Pre-existing tracker cookies survive after declining | The sweep only deletes cookies matching known patterns (`_ga`, `_fbp`, etc.). Unknown cookie names fall through. | Add the cookie to the scanner's known-cookies database via the admin UI, or extend the patterns in `blocker.ts`. |
