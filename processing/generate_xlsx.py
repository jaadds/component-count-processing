#!/usr/bin/env python3
"""
Generate the Choreo Component Count xlsx from formatted CSVs.

Usage:
    python3 generate_xlsx.py \
        --us <azure-formatted.csv> \
        --eu <aws-formatted.csv> \
        [--prev <previous.xlsx>] \
        [-o <output.xlsx>]

The --prev xlsx is used to carry forward manually curated fields
(Region, Data_Plane, Current Cloud, Owner, Internal/External, etc.)
for orgs that were already classified.
"""

import csv
import os
import sys
from collections import Counter

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


US_COLUMNS = [
    ' ', 'org_uuid', 'handle', 'Owner', 'Subscription Type', 'Internal/External',
    'Data_Plane', 'Current Cloud', 'Region', 'origin_cloud',
    'choreo-subscription-tier', 'devant-subscription-tier', 'bijira-subscription-tier',
    'componentTypeCount', 'componentTypeCategory',
    'Buildpack(.NET)', 'Buildpack(Go)', 'Buildpack(Java)', 'Buildpack(NodeJS)',
    'Buildpack(PHP)', 'Buildpack(Python)', 'Buildpack(Ruby)', 'Buildpack(Spring Boot)',
    'Buildpack(Ballerina)', 'Docker', 'Dockerless (React/Angular/Vue)',
    'Micro Integration', 'BYOI (Bring Your Own Image)', 'Prism Mock Service',
    'MCP', 'Git-based API proxy', 'API Specification/Scratch', 'Postman Collection',
    'External Consumer', 'Database',
]

EU_COLUMNS = [
    None, 'org_uuid', 'handle', 'Owner', 'Subscription Type', 'Internal/External',
    'Data_Plane', 'Cloud Classification', 'origin_cloud',
    'choreo-subscription-tier', 'devant-subscription-tier', 'bijira-subscription-tier',
    'componentTypeCount', 'componentTypeCategory',
    'Buildpack(.NET)', 'Buildpack(Go)', 'Buildpack(Java)', 'Buildpack(NodeJS)',
    'Buildpack(PHP)', 'Buildpack(Python)', 'Buildpack(Ruby)', 'Buildpack(Spring Boot)',
    'Buildpack(Ballerina)', 'Docker', 'Dockerless (React/Angular/Vue)',
    'Micro Integration', 'BYOI (Bring Your Own Image)', 'Prism Mock Service',
    'MCP', 'Git-based API proxy', 'API Specification/Scratch', 'Postman Collection',
    'External Consumer', 'Database',
]

CSV_TO_US_MAP = {
    ' ': ' ',
    'org_uuid': 'org_uuid',
    'handle': 'handle',
    'Owner': 'Owner',
    'Subscription Type': 'Subscription Type',
    'Internal/External': 'Internal/External',
    'Data_Plane': 'Data_Plane',
    'Current Cloud': 'Current Cloud',
    'Region': 'Region',
    'origin_cloud': 'origin_cloud',
    'choreo-subscription-tier': 'choreo-subscription-tier',
    'devant-subscription-tier': 'devant-subscription-tier',
    'bijira-subscription-tier': 'bijira-subscription-tier',
    'componentTypeCount': 'componentTypeCount',
    'componentTypeCategory': 'componentTypeCategory',
}

CSV_TO_EU_MAP = {
    ' ': None,
    'org_uuid': 'org_uuid',
    'handle': 'handle',
    'Owner': 'Owner',
    'Subscription Type': 'Subscription Type',
    'Internal/External': 'Internal/External',
    'Data_Plane': 'Data_Plane',
    'Current Cloud': 'Cloud Classification',
    'origin_cloud': 'origin_cloud',
    'choreo-subscription-tier': 'choreo-subscription-tier',
    'devant-subscription-tier': 'devant-subscription-tier',
    'bijira-subscription-tier': 'bijira-subscription-tier',
    'componentTypeCount': 'componentTypeCount',
    'componentTypeCategory': 'componentTypeCategory',
}

TECH_COLUMNS = [
    'Buildpack(.NET)', 'Buildpack(Go)', 'Buildpack(Java)', 'Buildpack(NodeJS)',
    'Buildpack(PHP)', 'Buildpack(Python)', 'Buildpack(Ruby)', 'Buildpack(Spring Boot)',
    'Buildpack(Ballerina)', 'Docker', 'Dockerless (React/Angular/Vue)',
    'Micro Integration', 'BYOI (Bring Your Own Image)', 'Prism Mock Service',
    'MCP', 'Git-based API proxy', 'API Specification/Scratch', 'Postman Collection',
    'External Consumer', 'Database',
]

MANUAL_FIELDS = ['Owner', 'Subscription Type', 'Internal/External', 'Data_Plane',
                 'Current Cloud', 'Region', 'Comment']


def load_prev_xlsx(xlsx_path):
    """Extract manual enrichment from previous xlsx, keyed by handle."""
    if not xlsx_path or not os.path.exists(xlsx_path):
        return {}

    wb = openpyxl.load_workbook(xlsx_path)
    lookup = {}

    if 'Choreo US' in wb.sheetnames:
        ws = wb['Choreo US']
        headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
            row_dict = dict(zip(headers, row))
            handle = row_dict.get('handle')
            if handle and handle not in lookup:
                lookup[handle] = {
                    'Owner': row_dict.get('Owner', ''),
                    'Subscription Type': row_dict.get('Subscription Type', ''),
                    'Internal/External': row_dict.get('Internal/External', ''),
                    'Data_Plane': row_dict.get('Data_Plane', ''),
                    'Current Cloud': row_dict.get('Current Cloud', ''),
                    'Region': row_dict.get('Region', ''),
                    'source': 'US',
                }

    if 'Choreo EU' in wb.sheetnames:
        ws = wb['Choreo EU']
        headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
            row_dict = dict(zip(headers, row))
            handle = row_dict.get('handle')
            if handle and handle not in lookup:
                lookup[handle] = {
                    'Owner': row_dict.get('Owner', ''),
                    'Subscription Type': row_dict.get('Subscription Type', ''),
                    'Internal/External': row_dict.get('Internal/External', ''),
                    'Data_Plane': row_dict.get('Data_Plane', ''),
                    'Current Cloud': row_dict.get('Cloud Classification', ''),
                    'Region': 'EU',
                    'source': 'EU',
                }

    wb.close()
    return lookup


def read_formatted_csv(csv_path):
    """Read formatted CSV and return list of row dicts."""
    rows = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(dict(r))
    return rows


def apply_prev_enrichment(rows, prev_lookup):
    """Apply manually curated fields from previous xlsx to rows."""
    current_handle = None
    for row in rows:
        handle = row.get('handle', '').strip()
        if handle:
            current_handle = handle

        if handle:
            if not row.get('Current Cloud', '').strip():
                row['Current Cloud'] = row.get('origin_cloud', '')

        if current_handle and current_handle in prev_lookup:
            prev = prev_lookup[current_handle]
            if handle:
                for field in MANUAL_FIELDS:
                    prev_val = prev.get(field)
                    if prev_val:
                        row[field] = prev_val


ROW_LEVEL_COLUMNS = set(TECH_COLUMNS + ['componentTypeCount', 'componentTypeCategory'])


def write_data_sheet(ws, rows, columns, col_map):
    """Write data rows into a worksheet, merging org-level cells."""
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color='D9E1F2', end_color='D9E1F2', fill_type='solid')
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)

    for col_idx, col_name in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill

    org_col_indices = []
    for col_idx, col_name in enumerate(columns, 1):
        if col_name not in ROW_LEVEL_COLUMNS:
            org_col_indices.append(col_idx)

    org_start_row = None
    org_end_row = None

    for row_idx, row_data in enumerate(rows, 2):
        handle = row_data.get('handle', '').strip()

        for col_idx, col_name in enumerate(columns, 1):
            csv_key = None
            for ck, xk in col_map.items():
                if xk == col_name:
                    csv_key = ck
                    break
            if csv_key is None and col_name in TECH_COLUMNS:
                csv_key = col_name

            if csv_key:
                val = row_data.get(csv_key, '')
                if col_name in TECH_COLUMNS or col_name == 'componentTypeCount':
                    try:
                        val = int(float(val)) if val != '' else 0
                    except (ValueError, TypeError):
                        val = 0
                elif val is None:
                    val = ''
                ws.cell(row=row_idx, column=col_idx, value=val if val != '' else None)

        if handle:
            if org_start_row is not None and org_end_row > org_start_row:
                for ci in org_col_indices:
                    ws.merge_cells(
                        start_row=org_start_row, start_column=ci,
                        end_row=org_end_row, end_column=ci)
                    ws.cell(row=org_start_row, column=ci).alignment = center_align
            org_start_row = row_idx
            org_end_row = row_idx
        else:
            if org_start_row is not None:
                org_end_row = row_idx

    if org_start_row is not None and org_end_row > org_start_row:
        for ci in org_col_indices:
            ws.merge_cells(
                start_row=org_start_row, start_column=ci,
                end_row=org_end_row, end_column=ci)
            ws.cell(row=org_start_row, column=ci).alignment = center_align

    ws.auto_filter.ref = ws.dimensions
    for col_idx in range(1, len(columns) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 14


def compute_component_counts(us_rows, eu_rows):
    """
    Count unique Enterprise & PAYG orgs by origin_cloud and region.
    Returns dict: {(infra, region): {'choreo': n, 'devant': n, 'bijira': n}}
    """
    ORIGIN_MAP = {
        'choreo': 'Choreo',
        'devant': 'Devant',
        'bijira': 'Bijira',
    }

    counts = {}

    def process_rows(rows, infra, default_region):
        seen = {}
        current_handle = None
        current_meta = {}

        for row in rows:
            handle = row.get('handle', '').strip()
            if handle:
                current_handle = handle
                current_meta = {
                    'sub_type': row.get('Subscription Type', '').strip(),
                    'origin': row.get('origin_cloud', '').strip().lower(),
                    'region': row.get('Region', '').strip() or default_region,
                }

            if current_handle and current_handle not in seen:
                if current_meta.get('sub_type') in ('Enterprise', 'PAYG'):
                    seen[current_handle] = current_meta

        for handle, meta in seen.items():
            origin_label = ORIGIN_MAP.get(meta['origin'], meta['origin'])
            region = meta['region']
            key = (infra, region)
            if key not in counts:
                counts[key] = Counter()
            counts[key][origin_label] += 1

    process_rows(us_rows, 'Azure', 'US')
    process_rows(eu_rows, 'AWS', 'EU')

    return counts


def write_component_counts_sheet(ws, counts):
    """Write the Component Counts summary sheet with formulas."""
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color='D9E1F2', end_color='D9E1F2', fill_type='solid')

    origins = ['Choreo', 'Devant', 'Bijira']

    azure_regions = sorted(set(r for (i, r) in counts if i == 'Azure'))
    aws_regions = sorted(set(r for (i, r) in counts if i == 'AWS'))

    current_row = 1

    def write_block(infra, regions, start_row):
        r = start_row
        ws.cell(row=r, column=1, value=infra).font = Font(bold=True, size=12)
        ws.cell(row=r, column=2, value='Enterprise & PAYG Accounts').font = header_font
        for ci, region in enumerate(regions):
            ws.cell(row=r, column=4 + ci, value=region).font = header_font
            ws.cell(row=r, column=4 + ci).fill = header_fill
        r += 1

        data_start = r
        for origin in origins:
            ws.cell(row=r, column=3, value=origin)
            for ci, region in enumerate(regions):
                key = (infra, region)
                val = counts.get(key, Counter()).get(origin, 0)
                ws.cell(row=r, column=4 + ci, value=val)
            r += 1
        data_end = r - 1

        for ci, region in enumerate(regions):
            col_letter = get_column_letter(4 + ci)
            ws.cell(row=r, column=4 + ci,
                    value=f'=SUM({col_letter}{data_start}:{col_letter}{data_end})')
            ws.cell(row=r, column=4 + ci).font = header_font
        r += 1

        ws.cell(row=r, column=2, value='Percentages').font = header_font
        for ci, region in enumerate(regions):
            ws.cell(row=r, column=4 + ci, value=region).font = header_font
            ws.cell(row=r, column=4 + ci).fill = header_fill
        r += 1

        total_row = data_end + 1
        for oi, origin in enumerate(origins):
            ws.cell(row=r, column=3, value=origin)
            for ci, region in enumerate(regions):
                col_letter = get_column_letter(4 + ci)
                data_cell = f'{col_letter}{data_start + oi}'
                total_cell = f'{col_letter}{total_row}'
                ws.cell(row=r, column=4 + ci,
                        value=f'={data_cell}/{total_cell}*100')
            r += 1

        return r + 1

    current_row = write_block('Azure', azure_regions if azure_regions else ['US'], current_row)
    current_row += 1
    write_block('AWS', aws_regions if aws_regions else ['EU'], current_row)

    for col in range(1, 10):
        ws.column_dimensions[get_column_letter(col)].width = 16


def main():
    us_csv = None
    eu_csv = None
    prev_xlsx = None
    output_file = None

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--us' and i + 1 < len(sys.argv):
            us_csv = sys.argv[i + 1]; i += 2
        elif sys.argv[i] == '--eu' and i + 1 < len(sys.argv):
            eu_csv = sys.argv[i + 1]; i += 2
        elif sys.argv[i] == '--prev' and i + 1 < len(sys.argv):
            prev_xlsx = sys.argv[i + 1]; i += 2
        elif sys.argv[i] == '-o' and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]; i += 2
        else:
            i += 1

    if not us_csv or not eu_csv:
        print(__doc__)
        sys.exit(1)

    if not output_file:
        output_file = 'Choreo Component Count - October.xlsx'

    prev_lookup = load_prev_xlsx(prev_xlsx)
    if prev_lookup:
        print(f'Loaded {len(prev_lookup)} orgs from previous xlsx')

    print(f'Reading US data: {us_csv}')
    us_rows = read_formatted_csv(us_csv)
    print(f'Reading EU data: {eu_csv}')
    eu_rows = read_formatted_csv(eu_csv)

    if prev_lookup:
        apply_prev_enrichment(us_rows, prev_lookup)
        apply_prev_enrichment(eu_rows, prev_lookup)

    wb = openpyxl.Workbook()

    ws_us = wb.active
    ws_us.title = 'Choreo US'
    write_data_sheet(ws_us, us_rows, US_COLUMNS, CSV_TO_US_MAP)
    print(f'Choreo US: {len(us_rows)} rows')

    ws_eu = wb.create_sheet('Choreo EU')
    write_data_sheet(ws_eu, eu_rows, EU_COLUMNS, CSV_TO_EU_MAP)
    print(f'Choreo EU: {len(eu_rows)} rows')

    counts = compute_component_counts(us_rows, eu_rows)
    ws_cc = wb.create_sheet('Component Counts')
    write_component_counts_sheet(ws_cc, counts)

    for (infra, region), c in sorted(counts.items()):
        print(f'  {infra} {region}: {dict(c)}')

    wb.save(output_file)
    print(f'\nSaved: {output_file}')


if __name__ == '__main__':
    main()
