#!/usr/bin/env python3
"""
Convert raw controlplane export CSV to the classification-ready format.

Usage:
    python3 format_for_classification.py <raw.csv> \
        [--emails <full-subscription-list.csv>] \
        [--sales <sales-revenue.csv>] \
        [--classification <classification.tsv>] \
        [--region <US|EU>] \
        [-o <output.csv>]
"""

import ast
import csv
import math
import os
import sys
from collections import defaultdict

COMPONENT_TYPE_HIERARCHY = {
    'buildpackService': ('Service', 'Buildpack'),
    'byocService': ('Service', 'Docker'),
    'ballerinaService': ('Service', 'Buildpack(Ballerina)'),
    'miApiService': ('Service', 'Micro Integration'),
    'byoiService': ('Service', 'BYOI (Bring Your Own Image)'),
    'prismMockService': ('Service', 'Prism Mock Service'),
    'buildpackWebApp': ('Web Application', 'Buildpack'),
    'byocWebApp': ('Web Application', 'Docker'),
    'byocWebAppsDockerfileLess': ('Web Application', 'Dockerless (React/Angular/Vue)'),
    'byoiWebApp': ('Web Application', 'BYOI (Bring Your Own Image)'),
    'buildpackCronjob': ('Scheduled Task', 'Buildpack'),
    'byocCronjob': ('Scheduled Task', 'Docker'),
    'scheduledTask': ('Scheduled Task', 'Buildpack(Ballerina)'),
    'byoiCronjob': ('Scheduled Task', 'BYOI (Bring Your Own Image)'),
    'mcpService': ('MCP Server', 'MCP'),
    'gitProxy': ('API Proxy', 'Git-based API proxy'),
    'proxy': ('API Proxy', 'API Specification/Scratch'),
    'restAPI': ('API Proxy', 'API Specification/Scratch'),
    'byocRestApi': ('API Proxy', 'Docker'),
    'webhook': ('Webhook', 'Buildpack(Ballerina)'),
    'buildpackWebhook': ('Webhook', 'Buildpack'),
    'buildpackJob': ('Manual Task', 'Buildpack'),
    'byocJob': ('Manual Task', 'Docker'),
    'manualTrigger': ('Manual Task', 'Buildpack(Ballerina)'),
    'byoiJob': ('Manual Task', 'BYOI (Bring Your Own Image)'),
    'buildpackEventHandler': ('Event Handler', 'Buildpack'),
    'ballerinaEventHandler': ('Event Handler', 'Buildpack(Ballerina)'),
    'byocTestRunnerDockerfileLess': ('Test Runner', 'Postman Collection'),
    'buildpackTestRunner': ('Test Runner', 'Buildpack'),
    'externalConsumer': ('External Consumer', 'External Consumer'),
    'byocTestRunner': ('Test Runner', 'Docker'),
    'database': ('Database', 'Database'),
    'graphql': ('Service', 'Buildpack(Ballerina)'),
    'byocEventHandler': ('Event Handler', 'Docker'),
    'byocWebhook': ('Webhook', 'Docker'),
    'miCronjob': ('Scheduled Task', 'Micro Integration'),
    'miEventHandler': ('Event Handler', 'Micro Integration'),
    'miJob': ('Manual Task', 'Micro Integration'),
    'miRestApi': ('API Proxy', 'Micro Integration'),
}

TECHNOLOGY_COLUMNS = [
    'Buildpack(.NET)', 'Buildpack(Go)', 'Buildpack(Java)', 'Buildpack(NodeJS)',
    'Buildpack(PHP)', 'Buildpack(Python)', 'Buildpack(Ruby)', 'Buildpack(Spring Boot)',
    'Buildpack(Ballerina)', 'Docker', 'Dockerless (React/Angular/Vue)',
    'Micro Integration', 'BYOI (Bring Your Own Image)', 'Prism Mock Service',
    'MCP', 'Git-based API proxy', 'API Specification/Scratch', 'Postman Collection',
    'External Consumer', 'Database',
]

OUTPUT_COLUMNS = [
    ' ', 'org_uuid', 'handle', 'Owner', 'Subscription Type', 'Internal/External',
    'Data_Plane', 'Current Cloud', 'Usecase', 'Revenue (Monthly)', 'API Traffic',
    'WebApp Traffic', 'Task Executions', 'Region', 'Comment',
    'origin_cloud', 'choreo-subscription-tier', 'devant-subscription-tier',
    'bijira-subscription-tier', 'componentTypeCount', 'componentTypeCategory',
] + TECHNOLOGY_COLUMNS


def parse_json_map(value):
    if isinstance(value, float) and math.isnan(value):
        return {}
    s = str(value).strip()
    if s in ('{}', '', '[]'):
        return {}
    try:
        return ast.literal_eval(s)
    except Exception:
        return {}


def parse_breakdown(value):
    if isinstance(value, float) and math.isnan(value):
        return []
    s = str(value).strip()
    if s in ('[]', '', '{}'):
        return []
    try:
        return ast.literal_eval(s)
    except Exception:
        return []


def safe_str(value):
    if value is None:
        return ''
    if isinstance(value, float) and math.isnan(value):
        return ''
    return str(value)


def derive_subscription_type(row):
    for col in ('choreo-subscription-tier', 'devant-subscription-tier', 'bijira-subscription-tier'):
        tier = safe_str(row.get(col, '')).strip()
        if tier == 'Enterprise':
            return 'Enterprise'
    for col in ('choreo-subscription-paid', 'devant-subscription-paid', 'bijira-subscription-paid'):
        if safe_str(row.get(col, '')).strip() == '1':
            return 'PAYG'
    return 'Free'


def derive_internal_external(owner_email, classification=''):
    if classification:
        c = classification.strip().lower()
        if c in ('internal', 'external'):
            return classification.strip().title()
    if owner_email and '@wso2.com' in owner_email.lower():
        return 'Internal'
    if owner_email:
        return 'External'
    return ''


def load_email_lookup(csv_path):
    if not csv_path or not os.path.exists(csv_path):
        return {}
    lookup = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            org_id = safe_str(r.get('Org-id', '')).strip()
            if org_id:
                lookup[org_id] = {
                    'Owner': safe_str(r.get('Owner Email', '')),
                    'Classification': safe_str(r.get('Classification', '')),
                }
    return lookup


def load_sales_lookup(csv_path):
    if not csv_path or not os.path.exists(csv_path):
        return {}
    lookup = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            org_id = safe_str(r.get('Org ID', '')).strip()
            if org_id:
                cdp_val = safe_str(r.get('CDP', '')).strip()
                if cdp_val == 'Yes':
                    lookup[org_id] = 'CDP'
                elif cdp_val == 'No':
                    lookup[org_id] = 'PDP'
    return lookup


def load_classification_tsv(tsv_path):
    """Load existing manual classification data keyed by handle."""
    if not tsv_path or not os.path.exists(tsv_path):
        return {}
    lookup = {}
    with open(tsv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for r in reader:
            handle = r.get('handle', '').strip()
            if not handle or handle in lookup:
                continue
            lookup[handle] = {
                'Owner': r.get('Owner', ''),
                'Internal/External': r.get('Internal/External', ''),
                'Data_Plane': r.get('Data_Plane', ''),
                'Cloud Classification': r.get('Cloud Classification', ''),
                'Comment': r.get('Comment', ''),
                'Subscription Type': r.get('Subscription Type', ''),
            }
    return lookup


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_csv = sys.argv[1]
    emails_csv = None
    sales_csv = None
    classification_tsv = None
    region = ''
    output_file = None

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--emails' and i + 1 < len(sys.argv):
            emails_csv = sys.argv[i + 1]; i += 2
        elif sys.argv[i] == '--sales' and i + 1 < len(sys.argv):
            sales_csv = sys.argv[i + 1]; i += 2
        elif sys.argv[i] == '--classification' and i + 1 < len(sys.argv):
            classification_tsv = sys.argv[i + 1]; i += 2
        elif sys.argv[i] == '--region' and i + 1 < len(sys.argv):
            region = sys.argv[i + 1]; i += 2
        elif sys.argv[i] == '-o' and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]; i += 2
        else:
            i += 1

    if not os.path.exists(input_csv):
        print(f'File not found: {input_csv}')
        sys.exit(1)

    email_lookup = load_email_lookup(emails_csv)
    sales_lookup = load_sales_lookup(sales_csv)
    class_lookup = load_classification_tsv(classification_tsv)

    if email_lookup:
        print(f'Loaded {len(email_lookup)} orgs from emails file')
    if sales_lookup:
        print(f'Loaded {len(sales_lookup)} orgs from sales file')
    if class_lookup:
        print(f'Loaded {len(class_lookup)} orgs from classification file')

    with open(input_csv) as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    print(f'Input: {len(raw_rows)} orgs from {input_csv}')

    unmapped = set()
    org_groups = []

    for r in raw_rows:
        ct_map = parse_json_map(r.get('componentType_counts_json', '{}'))
        if not ct_map:
            continue

        org_uuid = r['org_uuid']
        handle = r.get('handle', '')
        sub_type = derive_subscription_type(r)

        email_info = email_lookup.get(org_uuid, {})
        owner = email_info.get('Owner', '')
        classification = email_info.get('Classification', '')
        data_plane = sales_lookup.get(org_uuid, '')

        cls = class_lookup.get(handle, {})
        if cls.get('Owner'):
            owner = cls['Owner']
        if cls.get('Internal/External'):
            int_ext = cls['Internal/External']
        else:
            int_ext = derive_internal_external(owner, classification)
        if cls.get('Data_Plane'):
            data_plane = cls['Data_Plane']
        if cls.get('Subscription Type'):
            sub_type = cls['Subscription Type']

        comment = cls.get('Comment', '')
        current_cloud = cls.get('Cloud Classification', '')

        category_techs = defaultdict(lambda: defaultdict(int))

        for ctype, count in ct_map.items():
            if ctype in COMPONENT_TYPE_HIERARCHY:
                category, technology = COMPONENT_TYPE_HIERARCHY[ctype]
                if not ctype.startswith('buildpack'):
                    category_techs[category][technology] += count
            else:
                unmapped.add(ctype)

        bp_list = parse_breakdown(r.get('buildpack_component_breakdown_json', '[]'))
        for e in bp_list:
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

        rows_for_org = []
        for category in sorted(category_techs.keys()):
            techs = category_techs[category]
            total = sum(techs.get(tc, 0) for tc in TECHNOLOGY_COLUMNS)
            tech_vals = {tc: int(techs.get(tc, 0)) for tc in TECHNOLOGY_COLUMNS}

            rows_for_org.append({
                'category': category,
                'count': int(total),
                'techs': tech_vals,
            })

        if rows_for_org:
            org_groups.append({
                'org_uuid': org_uuid,
                'handle': handle,
                'owner': owner,
                'sub_type': sub_type,
                'int_ext': int_ext,
                'data_plane': data_plane,
                'current_cloud': current_cloud,
                'comment': comment,
                'origin_cloud': safe_str(r.get('origin_cloud', '')),
                'choreo_tier': safe_str(r.get('choreo-subscription-tier', '')),
                'devant_tier': safe_str(r.get('devant-subscription-tier', '')),
                'bijira_tier': safe_str(r.get('bijira-subscription-tier', '')),
                'region': region,
                'rows': rows_for_org,
            })

    org_groups.sort(key=lambda g: g['handle'].lower())

    if not output_file:
        base = os.path.splitext(os.path.basename(input_csv))[0]
        output_file = f'{base}-Formatted.csv'

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for org in org_groups:
            for idx, cat_row in enumerate(org['rows']):
                row = {col: '' for col in OUTPUT_COLUMNS}
                row[' '] = ''
                row['origin_cloud'] = org['origin_cloud']
                row['choreo-subscription-tier'] = org['choreo_tier']
                row['devant-subscription-tier'] = org['devant_tier']
                row['bijira-subscription-tier'] = org['bijira_tier']
                row['componentTypeCount'] = cat_row['count']
                row['componentTypeCategory'] = cat_row['category']
                for tc in TECHNOLOGY_COLUMNS:
                    row[tc] = cat_row['techs'][tc]

                if idx == 0:
                    row['org_uuid'] = org['org_uuid']
                    row['handle'] = org['handle']
                    row['Owner'] = org['owner']
                    row['Subscription Type'] = org['sub_type']
                    row['Internal/External'] = org['int_ext']
                    row['Data_Plane'] = org['data_plane']
                    row['Current Cloud'] = org['current_cloud']
                    row['Usecase'] = ''
                    row['Revenue (Monthly)'] = ''
                    row['API Traffic'] = ''
                    row['WebApp Traffic'] = ''
                    row['Task Executions'] = ''
                    row['Region'] = org['region']
                    row['Comment'] = org['comment']

                writer.writerow(row)

    unique_orgs = len(org_groups)
    total_rows = sum(len(g['rows']) for g in org_groups)
    print(f'Output: {total_rows} rows ({unique_orgs} orgs) -> {output_file}')

    if unmapped:
        print(f'\nUnmapped component types:')
        for u in sorted(unmapped):
            print(f'  {u}')


if __name__ == '__main__':
    main()
