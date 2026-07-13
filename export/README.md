# Export Subscription Details

Docker image that queries Choreo's MSSQL and MongoDB databases to export organization subscription details with component types and buildpack breakdowns.

## Setup

1. Copy `script.env.example` to `script.env` and fill in credentials:

```bash
cp script.env.example script.env
# Edit script.env with actual passwords
```

Credential sources:
- `MONGODB_PW` — project-manager's secret
- `MONGODB_HOST` — project-manager's config map
- `MONGODB_DATABASE` — project-manager's config map
- `MONGODB_USER` — project-manager's config map
- `SQL_SERVER_HOST` — app-dbs config map
- `SUBS_DB_PASSWORD` — subscription service's secret
- `APP_DB_PASSWORD` — app service's secret
- `CICD_DB_PASSWORD` — CICD service's secret

## Run

```bash
mkdir -p output

docker run --rm -it \
  --env-file script.env \
  -v "$PWD/output":/app/output \
  jaadds/subscription-export:1.0.0
```

This produces `org_subscriptions_with_components_and_buildpacks.csv` inside the `output/` folder.

## Build

```bash
docker build -t jaadds/subscription-export:1.0.0 .
```
