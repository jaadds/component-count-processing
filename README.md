# Choreo Component Details

Scripts to extract and analyze Choreo organization subscription data, component types, and buildpack usage.

## Structure

```
export/              Data extraction from Choreo DBs (runs in Docker)
processing/          Data transformation scripts (local Python)
asgardeo-lookup/     Org owner email lookups via Asgardeo
data/                Generated CSV outputs (gitignored)
```

## Workflow

### 1. Export raw data

Run the Docker-based export to pull subscription + component data from MSSQL and MongoDB. See [export/README.md](export/README.md).

Output: `org_subscriptions_with_components_and_buildpacks.csv`

### 2. Process data

All processing scripts read from and write to the `data/` directory.

**Expand component types with buildpack breakdown:**
```bash
python processing/process_all_components.py data/org_subscriptions_with_components_and_buildpacks.csv
```

**Buildpack-only pivot view:**
```bash
python processing/process_buildpacks.py data/org_subscriptions_with_components_and_buildpacks.csv
```

**Merge with subscription status data:**
```bash
python processing/combine_data.py
```

**Fill missing subscription data:**
```bash
python processing/update_combined_data.py
```

**Generate per-org overview for target organizations:**
```bash
python processing/generate_overview.py
```

### 3. Asgardeo lookups (optional)

Fetch org owner emails from Asgardeo's SQL database (requires Azure CLI auth):

```bash
cd asgardeo-lookup
./fetch_org_owner.sh ../data/organization-names.csv
./fetch_uuid_emails.sh prod-us
```

## Requirements

- Python 3.x with `pandas`
- Docker (for the export step)
- Azure CLI (for Asgardeo lookups)
