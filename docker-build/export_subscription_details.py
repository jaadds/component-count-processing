import os
import csv
import json
from collections import Counter
from urllib.parse import quote_plus

import pyodbc
from pymongo import MongoClient


# ======================================================================================
# CONFIG
# ======================================================================================

# Shared SQL Server host
SQL_SERVER_HOST = os.environ.get(
    "SQL_SERVER_HOST",
    "choreo-dev-ctrl-plane-mssql.database.windows.net"
)

# --- Subscriptions DB (subscriptionV2) ---
SUBS_DB_NAME = os.environ.get("SUBS_DB_NAME", "choreo_subscriptions_db")
SUBS_DB_USER = os.environ.get("SUBS_DB_USER", "choreo_subscriptions_db_user")
SUBS_DB_PASSWORD = os.environ.get("SUBS_DB_PASSWORD")  # must be set

# --- App DB (organization) ---
APP_DB_NAME = os.environ.get("APP_DB_NAME", "choreo_app_db")
APP_DB_USER = os.environ.get("APP_DB_USER", "choreo_app_db_user")
APP_DB_PASSWORD = os.environ.get("APP_DB_PASSWORD")  # must be set

# --- CICD DB (buildpack tables) ---
CICD_DB_NAME = os.environ.get("CICD_DB_NAME", "choreo_cicd_db")
CICD_DB_USER = os.environ.get("CICD_DB_USER", "choreo_cicd_admin_db_user")
CICD_DB_PASSWORD = os.environ.get("CICD_DB_PASSWORD")  # must be set

# --- MongoDB (components collection) ---
MONGO_HOST = os.environ.get("MONGODB_HOST", "choreo-apim-pl-1.hu3zq.mongodb.net")
MONGO_DB_NAME = os.environ.get("MONGODB_DATABASE", "DEV_DP_AUTH")
MONGO_USER = os.environ.get("MONGODB_USER", "dev_choreo_dp_auth")
MONGO_PASSWORD = os.environ.get("MONGODB_PW")  # must be set
MONGO_COMPONENTS_COLLECTION = os.environ.get("MONGODB_COMPONENTS_COLLECTION", "components")

# --- Output CSV (inside ./output directory) ---
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "org_subscriptions_with_components_and_buildpacks.csv")

# --- Subscription types of interest ---
SUBSCRIPTION_TYPES = [
    "choreo-subscription",
    "devant-subscription",
    "bijira-subscription",
]


# ======================================================================================
# CONNECTION HELPERS
# ======================================================================================

def _make_sql_conn(db_name, user, password_env_name, password_value):
    if not password_value:
        raise RuntimeError(f"{password_env_name} environment variable is not set")

    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER=tcp:{SQL_SERVER_HOST},1433;"
        f"DATABASE={db_name};"
        f"UID={user};"
        f"PWD={password_value};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


def get_subs_connection():
    # choreo_subscriptions_db
    return _make_sql_conn(
        SUBS_DB_NAME,
        SUBS_DB_USER,
        "SUBS_DB_PASSWORD",
        SUBS_DB_PASSWORD,
    )


def get_appdb_connection():
    # choreo_app_db
    return _make_sql_conn(
        APP_DB_NAME,
        APP_DB_USER,
        "APP_DB_PASSWORD",
        APP_DB_PASSWORD,
    )


def get_cicd_connection():
    # choreo_cicd_db
    return _make_sql_conn(
        CICD_DB_NAME,
        CICD_DB_USER,
        "CICD_DB_PASSWORD",
        CICD_DB_PASSWORD,
    )


def get_mongo_collection():
    if not MONGO_PASSWORD:
        raise RuntimeError("MONGODB_PW environment variable is not set")

    uri = (
        f"mongodb+srv://{MONGO_USER}:{quote_plus(MONGO_PASSWORD)}"
        f"@{MONGO_HOST}/{MONGO_DB_NAME}?retryWrites=true&w=majority"
    )
    client = MongoClient(uri)
    db = client[MONGO_DB_NAME]
    return db[MONGO_COMPONENTS_COLLECTION]


# ======================================================================================
# MSSQL: SUBSCRIPTIONS & ORG DETAILS
# ======================================================================================

def fetch_paid_subscriptions(conn):
    """
    From subscriptionV2, fetch (org_id, subscription_type) for rows where:
      - is_paid = 1
      - subscription_type in SUBSCRIPTION_TYPES
    """
    placeholders = ",".join("?" for _ in SUBSCRIPTION_TYPES)
    sql = f"""
        SELECT org_id, subscription_type
        FROM subscriptionV2
        WHERE is_paid = 1
          AND subscription_type IN ({placeholders})
    """

    cur = conn.cursor()
    cur.execute(sql, SUBSCRIPTION_TYPES)
    rows = cur.fetchall()
    cur.close()
    return [(r.org_id, r.subscription_type) for r in rows]


def build_org_paid_flags(rows):
    """
    rows: list of (org_id, subscription_type)

    Returns:
      org_uuid -> {
        "choreo-subscription-paid": 0/1,
        "devant-subscription-paid": 0/1,
        "bijira-subscription-paid": 0/1,
      }
    """
    orgs = {}

    for org_id, subscription_type in rows:
        if org_id not in orgs:
            orgs[org_id] = {
                "choreo-subscription-paid": 0,
                "devant-subscription-paid": 0,
                "bijira-subscription-paid": 0,
            }

        if subscription_type == "choreo-subscription":
            orgs[org_id]["choreo-subscription-paid"] = 1
        elif subscription_type == "devant-subscription":
            orgs[org_id]["devant-subscription-paid"] = 1
        elif subscription_type == "bijira-subscription":
            orgs[org_id]["bijira-subscription-paid"] = 1

    return orgs


def fetch_org_details(conn, org_uuid):
    """
    From choreo_app_db.organization, fetch:
      - id (numeric id)
      - handle
      - origin_cloud

    Returns (id, handle, origin_cloud) or (None, None, None) if not found.
    """
    sql = """
        SELECT id, handle, origin_cloud
        FROM organization
        WHERE uuid = ?
    """
    cur = conn.cursor()
    cur.execute(sql, org_uuid)
    row = cur.fetchone()
    cur.close()

    if row:
        return row.id, row.handle, row.origin_cloud
    else:
        return None, None, None


# ======================================================================================
# MONGODB: COMPONENT SUMMARY PER ORG
# ======================================================================================

def get_component_summary_for_org(coll, org_numeric_id):
    """
    For a given org_numeric_id (organization.id from MSSQL),
    produce:

      - total_components
      - metadata_null_count
      - originCloud_null_count
      - componentType_counts_json
      - originCloud_counts_json
    """
    empty = {
        "total_components": 0,
        "metadata_null_count": 0,
        "originCloud_null_count": 0,
        "componentType_counts_json": "{}",
        "originCloud_counts_json": "{}",
    }

    if org_numeric_id is None:
        return empty

    pipeline = [
        {"$match": {"organizationId": org_numeric_id}},
        {
            "$facet": {
                "totalComponents": [
                    {"$count": "count"}
                ],
                "metadataNull": [
                    {"$match": {"metadata": None}},
                    {"$count": "count"}
                ],
                "byComponentType": [
                    {
                        "$group": {
                            "_id": "$componentType",
                            "count": {"$sum": 1}
                        }
                    }
                ],
                "originCloudNull": [
                    {
                        "$match": {
                            "metadata": {"$ne": None},
                            "metadata.originCloud": None
                        }
                    },
                    {"$count": "count"}
                ],
                "originCloudGroups": [
                    {
                        "$match": {
                            "metadata": {"$ne": None},
                            "metadata.originCloud": {"$ne": None}
                        }
                    },
                    {
                        "$group": {
                            "_id": "$metadata.originCloud",
                            "count": {"$sum": 1}
                        }
                    }
                ]
            }
        }
    ]

    res = list(coll.aggregate(pipeline))
    if not res:
        return empty

    agg = res[0]

    total_components = (
        agg.get("totalComponents", [{}])[0].get("count", 0)
        if agg.get("totalComponents") else 0
    )

    metadata_null_count = (
        agg.get("metadataNull", [{}])[0].get("count", 0)
        if agg.get("metadataNull") else 0
    )

    originCloud_null_count = (
        agg.get("originCloudNull", [{}])[0].get("count", 0)
        if agg.get("originCloudNull") else 0
    )

    comp_type_counts = {}
    for item in agg.get("byComponentType", []):
        key = item.get("_id")
        count = item.get("count", 0)
        if key is not None:
            comp_type_counts[str(key)] = count

    origin_cloud_counts = {}
    for item in agg.get("originCloudGroups", []):
        key = item.get("_id")
        count = item.get("count", 0)
        if key is not None:
            origin_cloud_counts[str(key)] = count

    return {
        "total_components": total_components,
        "metadata_null_count": metadata_null_count,
        "originCloud_null_count": originCloud_null_count,
        "componentType_counts_json": json.dumps(comp_type_counts),
        "originCloud_counts_json": json.dumps(origin_cloud_counts),
    }


# ======================================================================================
# MONGO + CICD: BUILDPACK BREAKDOWN PER ORG
# ======================================================================================

def get_buildpack_components_for_org(mongo_coll, org_numeric_id):
    """
    Returns list of dicts for buildpack components in this org:
      [
        { "componentId": "<id>", "componentType": "buildpackEventHandler" },
        ...
      ]

    Buildpack components = componentType containing 'buildpack'.
    Join key to CICD DB = 'id' field from Mongo.
    """
    if org_numeric_id is None:
        return []

    cursor = mongo_coll.find(
        {
            "organizationId": org_numeric_id,
            "componentType": {"$regex": "buildpack", "$options": "i"},
        },
        {"id": 1, "componentType": 1},
    )

    result = []
    for doc in cursor:
        cid = doc.get("id")
        ctype = doc.get("componentType")
        if cid and ctype:
            result.append({
                "componentId": str(cid),
                "componentType": str(ctype),
            })
    return result


def fetch_buildpack_display_for_components(cicd_conn, component_ids):
    """
    Given a list of componentIds (strings), query choreo_cicd_db:

      buildpack_build_detail (componentId -> buildpackId)
      join buildpack (id -> displayName)

    Returns dict:
      componentId -> displayName
    """
    if not component_ids:
        return {}

    mapping = {}
    CHUNK_SIZE = 1000
    cur = cicd_conn.cursor()

    for i in range(0, len(component_ids), CHUNK_SIZE):
        chunk = component_ids[i:i + CHUNK_SIZE]
        placeholders = ",".join("?" for _ in chunk)

        sql = f"""
            SELECT bbd.componentId, bp.displayName
            FROM buildpack_build_detail bbd
            JOIN buildpack bp ON bp.id = bbd.buildpackId
            WHERE bbd.componentId IN ({placeholders})
        """

        cur.execute(sql, chunk)
        for row in cur.fetchall():
            mapping[str(row.componentId)] = row.displayName

    cur.close()
    return mapping


def get_buildpack_summary_for_org(mongo_coll, cicd_conn, org_numeric_id):
    """
    For a given org numeric id, returns:

      - buildpack_component_count
      - buildpack_component_breakdown_json

    Where breakdown is grouped by (componentType, buildpack.displayName).
    """
    empty = {
        "buildpack_component_count": 0,
        "buildpack_component_breakdown_json": "[]",
    }

    if org_numeric_id is None:
        return empty

    comps = get_buildpack_components_for_org(mongo_coll, org_numeric_id)
    if not comps:
        return empty

    component_ids = [c["componentId"] for c in comps]
    bp_map = fetch_buildpack_display_for_components(cicd_conn, component_ids)

    # Group by (componentType, displayName)
    counter = Counter()
    for c in comps:
        cid = c["componentId"]
        ctype = c["componentType"]
        display_name = bp_map.get(cid, "UNKNOWN")
        counter[(ctype, display_name)] += 1

    breakdown_list = []
    for (ctype, display_name), count in counter.items():
        breakdown_list.append({
            "componentType": ctype,
            "buildpack": display_name,
            "count": count,
        })

    return {
        "buildpack_component_count": sum(counter.values()),
        "buildpack_component_breakdown_json": json.dumps(breakdown_list),
    }


# ======================================================================================
# CSV WRITER
# ======================================================================================

def write_output_csv(org_summaries, appdb_conn, mongo_coll, cicd_conn):
    """
    org_summaries: dict returned by build_org_paid_flags()
    appdb_conn: connection to choreo_app_db
    mongo_coll: MongoDB components collection
    cicd_conn: connection to choreo_cicd_db
    """
    fieldnames = [
        "org_uuid",
        "org_numeric_id",
        "handle",
        "origin_cloud",
        "choreo-subscription-paid",
        "devant-subscription-paid",
        "bijira-subscription-paid",
        "total_components",
        "metadata_null_count",
        "originCloud_null_count",
        "componentType_counts_json",
        "originCloud_counts_json",
        "buildpack_component_count",
        "buildpack_component_breakdown_json",
    ]

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for org_uuid, paid_flags in org_summaries.items():
            numeric_id, handle, origin_cloud = fetch_org_details(appdb_conn, org_uuid)

            comp_summary = get_component_summary_for_org(mongo_coll, numeric_id)
            bp_summary = get_buildpack_summary_for_org(mongo_coll, cicd_conn, numeric_id)

            row = {
                "org_uuid": org_uuid,
                "org_numeric_id": numeric_id if numeric_id is not None else "",
                "handle": handle if handle is not None else "",
                "origin_cloud": origin_cloud if origin_cloud is not None else "",
                "choreo-subscription-paid": paid_flags["choreo-subscription-paid"],
                "devant-subscription-paid": paid_flags["devant-subscription-paid"],
                "bijira-subscription-paid": paid_flags["bijira-subscription-paid"],
                "total_components": comp_summary["total_components"],
                "metadata_null_count": comp_summary["metadata_null_count"],
                "originCloud_null_count": comp_summary["originCloud_null_count"],
                "componentType_counts_json": comp_summary["componentType_counts_json"],
                "originCloud_counts_json": comp_summary["originCloud_counts_json"],
                "buildpack_component_count": bp_summary["buildpack_component_count"],
                "buildpack_component_breakdown_json": bp_summary["buildpack_component_breakdown_json"],
            }

            writer.writerow(row)


# ======================================================================================
# MAIN
# ======================================================================================

def main():
    # 1. Paid subscriptions
    subs_conn = get_subs_connection()
    try:
        paid_rows = fetch_paid_subscriptions(subs_conn)
        org_summaries = build_org_paid_flags(paid_rows)
        print(f"Found {len(org_summaries)} orgs with at least one paid subscription.")
    finally:
        subs_conn.close()

    # 2. App DB + Mongo + CICD
    app_conn = get_appdb_connection()
    mongo_coll = get_mongo_collection()
    cicd_conn = get_cicd_connection()

    try:
        write_output_csv(org_summaries, app_conn, mongo_coll, cicd_conn)
    finally:
        app_conn.close()
        cicd_conn.close()

    print(f"Written merged CSV with component & buildpack summary to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

