#!/usr/bin/env python3
import pandas as pd
import ast
import sys
import os
import math
from collections import defaultdict

COMPONENT_TYPE_HIERARCHY = {
    # Service
    'buildpackService': ('Service', 'Buildpack'),
    'byocService': ('Service', 'Docker'),
    'ballerinaService': ('Service', 'Buildpack(Ballerina)'),
    'miApiService': ('Service', 'Micro Integration'),
    'byoiService': ('Service', 'BYOI (Bring Your Own Image)'),
    'prismMockService': ('Service', 'Prism Mock Service'),
    # Web Application
    'buildpackWebApp': ('Web Application', 'Buildpack'),
    'byocWebApp': ('Web Application', 'Docker'),
    'byocWebAppsDockerfileLess': ('Web Application', 'Dockerless (React/Angular/Vue)'),
    'byoiWebApp': ('Web Application', 'BYOI (Bring Your Own Image)'),
    # Scheduled Task
    'buildpackCronjob': ('Scheduled Task', 'Buildpack'),
    'byocCronjob': ('Scheduled Task', 'Docker'),
    'scheduledTask': ('Scheduled Task', 'Buildpack(Ballerina)'),
    'byoiCronjob': ('Scheduled Task', 'BYOI (Bring Your Own Image)'),
    # MCP Server
    'mcpService': ('MCP Server', 'MCP'),
    # API Proxy
    'gitProxy': ('API Proxy', 'Git-based API proxy'),
    'proxy': ('API Proxy', 'API Specification/Scratch'),
    'restAPI': ('API Proxy', 'API Specification/Scratch'),
    'byocRestApi': ('API Proxy', 'Docker'),
    # Webhook
    'webhook': ('Webhook', 'Buildpack(Ballerina)'),
    'buildpackWebhook': ('Webhook', 'Buildpack'),
    # Manual Task
    'buildpackJob': ('Manual Task', 'Buildpack'),
    'byocJob': ('Manual Task', 'Docker'),
    'manualTrigger': ('Manual Task', 'Buildpack(Ballerina)'),
    'byoiJob': ('Manual Task', 'BYOI (Bring Your Own Image)'),
    # Event Handler
    'buildpackEventHandler': ('Event Handler', 'Buildpack'),
    'ballerinaEventHandler': ('Event Handler', 'Buildpack(Ballerina)'),
    # Test Runner
    'byocTestRunnerDockerfileLess': ('Test Runner', 'Postman Collection'),
    'buildpackTestRunner': ('Test Runner', 'Buildpack'),
    # External Consumer
    'externalConsumer': ('External Consumer', 'External Consumer'),
    # Test Runner
    'byocTestRunner': ('Test Runner', 'Docker'),
    # Database
    'database': ('Database', 'Database'),
    # GraphQL (deprecated Ballerina type)
    'graphql': ('Service', 'Buildpack(Ballerina)'),
    # BYOC (Docker) variants
    'byocEventHandler': ('Event Handler', 'Docker'),
    'byocWebhook': ('Webhook', 'Docker'),
    # Micro Integration variants
    'miCronjob': ('Scheduled Task', 'Micro Integration'),
    'miEventHandler': ('Event Handler', 'Micro Integration'),
    'miJob': ('Manual Task', 'Micro Integration'),
    'miRestApi': ('API Proxy', 'Micro Integration'),
}

TECHNOLOGY_COLUMNS = [
    'Buildpack(.NET)',
    'Buildpack(Go)',
    'Buildpack(Java)',
    'Buildpack(NodeJS)',
    'Buildpack(PHP)',
    'Buildpack(Python)',
    'Buildpack(Ruby)',
    'Buildpack(Spring Boot)',
    'Buildpack(Ballerina)',
    'Docker',
    'Dockerless (React/Angular/Vue)',
    'Micro Integration',
    'BYOI (Bring Your Own Image)',
    'Prism Mock Service',
    'MCP',
    'Git-based API proxy',
    'API Specification/Scratch',
    'Postman Collection',
    'External Consumer',
    'Database',
]


def parse_json_map(value):
    if isinstance(value, float) and math.isnan(value):
        return {}
    s = str(value).strip()
    if s in ("{}", "", "[]"):
        return {}
    try:
        return ast.literal_eval(s)
    except Exception:
        return {}


def parse_breakdown(value):
    if isinstance(value, float) and math.isnan(value):
        return []
    s = str(value).strip()
    if s in ("[]", "", "{}"):
        return []
    try:
        return ast.literal_eval(s)
    except Exception:
        return []


def safe_str(value):
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value) if value is not None else ""


def derive_customer_type(row):
    for col in ['choreo-subscription-tier', 'devant-subscription-tier', 'bijira-subscription-tier']:
        tier = safe_str(row.get(col, '')).strip()
        if tier == 'Enterprise':
            return 'Enterprise'
    return 'PAYG'


def load_email_classification(csv_path):
    """Load Owner Email and Classification from full-subscription-list.csv."""
    if not csv_path or not os.path.exists(csv_path):
        return {}
    df = pd.read_csv(csv_path)
    lookup = {}
    for _, r in df.iterrows():
        org_id = safe_str(r.get('Org-id', '')).strip()
        if org_id:
            lookup[org_id] = {
                'Owner': safe_str(r.get('Owner Email', '')),
                'Classification': safe_str(r.get('Classification', '')),
            }
    return lookup


def load_cdp_pdp(csv_path):
    """Load CDP/PDP info from sales-revenue CSV."""
    if not csv_path or not os.path.exists(csv_path):
        return {}
    df = pd.read_csv(csv_path)
    lookup = {}
    for _, r in df.iterrows():
        org_id = safe_str(r.get('Org ID', '')).strip()
        if org_id:
            cdp_val = safe_str(r.get('CDP', '')).strip()
            if cdp_val == 'Yes':
                lookup[org_id] = 'CDP'
            elif cdp_val == 'No':
                lookup[org_id] = 'PDP'
    return lookup


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process_components.py <input.csv> [--emails <emails.csv>] [--sales <sales.csv>]")
        sys.exit(1)

    input_csv = sys.argv[1]
    if not os.path.exists(input_csv):
        print(f"File not found: {input_csv}")
        sys.exit(1)

    emails_csv = None
    sales_csv = None
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--emails' and i + 1 < len(sys.argv):
            emails_csv = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--sales' and i + 1 < len(sys.argv):
            sales_csv = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    print(f"Processing: {input_csv}")

    email_lookup = load_email_classification(emails_csv)
    if email_lookup:
        print(f"Loaded {len(email_lookup)} orgs from emails file")

    cdp_lookup = load_cdp_pdp(sales_csv)
    if cdp_lookup:
        print(f"Loaded {len(cdp_lookup)} orgs from sales file (CDP/PDP)")

    df = pd.read_csv(input_csv)

    org_cols = ['org_uuid', 'org_numeric_id', 'handle', 'origin_cloud']
    tier_cols = ['choreo-subscription-tier', 'devant-subscription-tier', 'bijira-subscription-tier']

    unmapped = set()
    result_rows = []

    for _, r in df.iterrows():
        ct_map = parse_json_map(r.get('componentType_counts_json', '{}'))
        if not ct_map:
            continue

        org_uuid = str(r['org_uuid'])
        customer_type = derive_customer_type(r)
        org_data = {col: r[col] for col in org_cols}
        org_data['Customer_Type'] = customer_type

        email_info = email_lookup.get(org_uuid, {})
        org_data['Classification'] = email_info.get('Classification', '')
        org_data['Owner'] = email_info.get('Owner', '')
        org_data['Data_Plane'] = cdp_lookup.get(org_uuid, '')

        for tc in tier_cols:
            org_data[tc] = safe_str(r.get(tc, ''))

        category_techs = defaultdict(lambda: defaultdict(int))

        for ctype, count in ct_map.items():
            if ctype in COMPONENT_TYPE_HIERARCHY:
                category, technology = COMPONENT_TYPE_HIERARCHY[ctype]
                if not ctype.startswith('buildpack'):
                    category_techs[category][technology] += count
            else:
                unmapped.add(ctype)

        lst = parse_breakdown(r.get('buildpack_component_breakdown_json', '[]'))
        for e in lst:
            if not isinstance(e, dict):
                continue
            ctype = e.get('componentType')
            if not isinstance(ctype, str) or ctype not in COMPONENT_TYPE_HIERARCHY:
                if ctype:
                    unmapped.add(ctype)
                continue
            category, technology = COMPONENT_TYPE_HIERARCHY[ctype]
            if technology == 'Buildpack':
                bp = e.get('buildpack') or 'UNKNOWN'
                category_techs[category][f'Buildpack({bp})'] += e.get('count', 1)

        for category, techs in category_techs.items():
            row = org_data.copy()
            row['componentTypeCategory'] = category
            total = 0
            for tc in TECHNOLOGY_COLUMNS:
                val = techs.get(tc, 0)
                row[tc] = int(val)
                total += val
            row['componentTypeCount'] = int(total)
            result_rows.append(row)

    result = pd.DataFrame(result_rows)

    meta_cols = (['org_uuid', 'org_numeric_id', 'handle', 'Classification', 'Owner',
                  'Customer_Type', 'Data_Plane', 'origin_cloud'] +
                 tier_cols +
                 ['componentTypeCount', 'componentTypeCategory'])
    result = result[meta_cols + TECHNOLOGY_COLUMNS]
    result = result.fillna('')
    result = result.sort_values(['handle', 'componentTypeCategory'])

    base = os.path.splitext(os.path.basename(input_csv))[0]
    out_dir = os.path.join(os.path.dirname(input_csv) or '.', 'output')
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"{base}_overview.csv")
    result.to_csv(out_file, index=False)

    print(f"Input orgs: {len(df)}")
    print(f"Orgs with components: {result['org_uuid'].nunique()}")
    print(f"Output rows: {len(result)}")
    print(f"Output: {out_file}")

    print(f"\nCustomer_Type distribution:")
    for ct, count in result.groupby('Customer_Type')['org_uuid'].nunique().items():
        print(f"  {ct}: {count} orgs")

    if email_lookup:
        classified = result[result['Classification'] != '']['org_uuid'].nunique()
        print(f"\nClassification: {classified} orgs matched")

    if cdp_lookup:
        dp_matched = result[result['Data_Plane'] != '']['org_uuid'].nunique()
        print(f"Data_Plane: {dp_matched} orgs matched (CDP/PDP)")

    if unmapped:
        print(f"\nUnmapped component types:")
        for u in sorted(unmapped):
            print(f"  {u}")


if __name__ == "__main__":
    main()
