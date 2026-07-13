#!/usr/bin/env python3
import csv
import ast
import math
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

TARGET_HANDLES = {"bgic", "devryuniversity", "fatorseguradora", "holmesglen", "pldtpdp", "universityofedinburgh", "wiprotechnologies", "wiprosos", "zimi"}

COMPONENT_TYPE_MAP = {
    "buildpackService":           ("Service", None),
    "buildpackWebApp":            ("Web Application", None),
    "buildpackCronjob":           ("Scheduled Task", None),
    "buildpackWebhook":           ("Webhook", None),
    "ballerinaService":           ("Service", "Buildpack(Ballerina)"),
    "scheduledTask":              ("Scheduled Task", "Buildpack(Ballerina)"),
    "manualTrigger":              ("Manual Task", "Buildpack(Ballerina)"),
    "webhook":                    ("Webhook", "Buildpack(Ballerina)"),
    "byocService":                ("Service", "Docker"),
    "byocWebApp":                 ("Web Application", "Docker"),
    "byocWebAppsDockerfileLess":  ("Web Application", "Dockerless (React/Angular/Vue)"),
    "byocEventHandler":           ("Event Handler", "Docker"),
    "byocCronjob":                ("Scheduled Task", "Docker"),
    "byocRestApi":                ("Service", "Docker"),
    "byoiService":                ("Service", "BYOI (Bring Your Own Image)"),
    "byoiWebApp":                 ("Web Application", "BYOI (Bring Your Own Image)"),
    "byoiCronjob":                ("Scheduled Task", "BYOI (Bring Your Own Image)"),
    "miApiService":               ("Service", "Micro Integration"),
    "miCronjob":                  ("Scheduled Task", "Micro Integration"),
    "miEventHandler":             ("Event Handler", "Micro Integration"),
    "miJob":                      ("Manual Task", "Micro Integration"),
    "proxy":                      ("API Proxy", "API Specification/Scratch"),
    "gitProxy":                   ("API Proxy", "Git-based API proxy"),
    "restAPI":                    ("Service", "API Specification/Scratch"),
    "prismMockService":           ("Service", "Prism Mock Service"),
    "externalConsumer":           ("External Consumer", "External Consumer"),
    "mcpService":                 ("Service", "MCP"),
    "byocTestRunnerDockerfileLess": ("Service", "Docker"),
    "byoiCronjob":                ("Scheduled Task", "BYOI (Bring Your Own Image)"),
}

BUILDPACK_COLUMNS = [
    "Buildpack(.NET)", "Buildpack(Go)", "Buildpack(Java)", "Buildpack(NodeJS)",
    "Buildpack(PHP)", "Buildpack(Python)", "Buildpack(Ruby)", "Buildpack(Spring Boot)",
    "Buildpack(Ballerina)",
]

DETAIL_COLUMNS = BUILDPACK_COLUMNS + [
    "Docker", "Dockerless (React/Angular/Vue)", "Micro Integration",
    "BYOI (Bring Your Own Image)", "Prism Mock Service", "MCP",
    "Git-based API proxy", "API Specification/Scratch", "Postman Collection",
    "External Consumer", "Database",
]

BUILDPACK_NAME_TO_COL = {
    ".NET":        "Buildpack(.NET)",
    "Go":          "Buildpack(Go)",
    "Java":        "Buildpack(Java)",
    "NodeJS":      "Buildpack(NodeJS)",
    "PHP":         "Buildpack(PHP)",
    "Python":      "Buildpack(Python)",
    "Ruby":        "Buildpack(Ruby)",
    "Spring Boot": "Buildpack(Spring Boot)",
    "Ballerina":   "Buildpack(Ballerina)",
}

OUTPUT_COLUMNS = [
    "org_uuid", "org_numeric_id", "handle", "Classification", "Owner", "Paying",
    "Customer_Type", "origin_cloud", "Paid Choreo Subscription", "Paid Devant Subscription",
    "Paid Bijira Subscription", "componentTypeCount", "componentTypeCategory",
] + DETAIL_COLUMNS


def parse_json(value):
    if isinstance(value, float) and math.isnan(value):
        return {}
    s = str(value).strip()
    if s in ("{}", "", "[]"):
        return {} if s != "[]" else []
    try:
        return ast.literal_eval(s)
    except Exception:
        return {} if s.startswith("{") else []


def load_metadata():
    meta = {}
    with open(os.path.join(DATA_DIR, "combined_components_and_subscription.csv")) as f:
        reader = csv.DictReader(f)
        for r in reader:
            h = r["handle"]
            if h in TARGET_HANDLES and h not in meta:
                meta[h] = {
                    "Classification": r.get("Classification", ""),
                    "Owner": r.get("Owner", ""),
                    "Paying": r.get("Paying", ""),
                }
    return meta


def main():
    input_csv = os.path.join(DATA_DIR, "org_subscriptions_with_components_and_buildpacks-2026-05-19.csv")
    metadata = load_metadata()

    org_rows = []
    with open(input_csv) as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["handle"] in TARGET_HANDLES:
                org_rows.append(r)

    if not org_rows:
        print("No matching orgs found.")
        sys.exit(1)

    output_rows = []
    for r in org_rows:
        handle = r["handle"]
        meta = metadata.get(handle, {})

        is_paying = (
            r.get("choreo-subscription-paid", "0") == "1"
            or r.get("devant-subscription-paid", "0") == "1"
            or r.get("bijira-subscription-paid", "0") == "1"
        )

        base = {
            "org_uuid": r["org_uuid"],
            "org_numeric_id": r["org_numeric_id"],
            "handle": handle,
            "Classification": meta.get("Classification", ""),
            "Owner": meta.get("Owner", ""),
            "Paying": "Yes" if is_paying else "No",
            "Customer_Type": "",
            "origin_cloud": r["origin_cloud"],
            "Paid Choreo Subscription": r["choreo-subscription-paid"],
            "Paid Devant Subscription": r["devant-subscription-paid"],
            "Paid Bijira Subscription": r["bijira-subscription-paid"],
        }

        ct_map = parse_json(r.get("componentType_counts_json", "{}"))
        if not ct_map:
            continue

        bp_breakdown = parse_json(r.get("buildpack_component_breakdown_json", "[]"))
        bp_by_type = {}
        for entry in bp_breakdown:
            if not isinstance(entry, dict):
                continue
            ctype = entry.get("componentType", "")
            bp_name = entry.get("buildpack", "")
            count = entry.get("count", 0)
            bp_by_type.setdefault(ctype, []).append((bp_name, count))

        category_detail = {}

        for ctype, count in ct_map.items():
            mapping = COMPONENT_TYPE_MAP.get(ctype)
            if not mapping:
                print(f"WARNING: unmapped componentType '{ctype}' for org '{handle}'", file=sys.stderr)
                continue

            category, detail_col = mapping

            if category not in category_detail:
                category_detail[category] = {col: 0 for col in DETAIL_COLUMNS}
                category_detail[category]["_total"] = 0

            if ctype.startswith("buildpack"):
                bp_entries = bp_by_type.get(ctype, [])
                bp_sum = 0
                for bp_name, bp_count in bp_entries:
                    col = BUILDPACK_NAME_TO_COL.get(bp_name)
                    if col:
                        category_detail[category][col] += bp_count
                        bp_sum += bp_count
                remainder = count - bp_sum
                if remainder > 0:
                    category_detail[category]["Buildpack(Ballerina)"] += 0
                category_detail[category]["_total"] += count
            else:
                if detail_col:
                    category_detail[category][detail_col] += count
                category_detail[category]["_total"] += count

        for category, details in sorted(category_detail.items()):
            row = dict(base)
            row["componentTypeCategory"] = category
            row["componentTypeCount"] = details["_total"]
            for col in DETAIL_COLUMNS:
                row[col] = details[col]
            output_rows.append(row)

    output_file = os.path.join(DATA_DIR, "target_orgs_overview.csv")
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Written {len(output_rows)} rows to {output_file}")
    for r in output_rows:
        print(f"  {r['handle']} | {r['componentTypeCategory']} | count={r['componentTypeCount']}")


if __name__ == "__main__":
    main()
