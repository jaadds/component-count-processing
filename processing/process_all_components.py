#!/usr/bin/env python3
import pandas as pd
import ast
import sys
import os
import math
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------
def parse_json_map(value):
    """Parse componentType_counts_json like '{"proxy": 7, "restAPI": 2}' into a dict."""
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
    """Parse buildpack_component_breakdown_json into a list of dicts."""
    if isinstance(value, float) and math.isnan(value):
        return []
    s = str(value).strip()
    if s in ("[]", "", "{}"):
        return []
    try:
        return ast.literal_eval(s)
    except Exception:
        return []


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_buildpacks.py <input.csv>")
        sys.exit(1)

    input_csv = sys.argv[1]

    if not os.path.exists(input_csv):
        print(f"File not found: {input_csv}")
        sys.exit(1)

    print(f"Processing file: {input_csv}")

    # ---------------------------------------------------------
    # 1) Load CSV
    # ---------------------------------------------------------
    df = pd.read_csv(input_csv)

    org_cols = [
        "org_uuid",
        "org_numeric_id",
        "handle",
        "origin_cloud",
        "choreo-subscription-paid",
        "devant-subscription-paid",
        "bijira-subscription-paid",
    ]

    # ---------------------------------------------------------
    # 2) Base table: one row per org + componentType
    #     using componentType_counts_json
    # ---------------------------------------------------------
    base_rows = []
    for _, r in df.iterrows():
        ct_map = parse_json_map(r.get("componentType_counts_json", "{}"))
        if not ct_map:
            # org with zero components -> no rows
            continue

        org_data = {col: r[col] for col in org_cols}
        for ctype, count in ct_map.items():
            rec = org_data.copy()
            rec["componentTypeName"] = ctype
            rec["component_count"] = count
            base_rows.append(rec)

    if not base_rows:
        print("No componentType data found in componentType_counts_json.")
        sys.exit(0)

    df_types = pd.DataFrame(base_rows)

    # ---------------------------------------------------------
    # 3) Build breakdown table per org + componentType + buildpack
    # ---------------------------------------------------------
    bp_rows = []
    flavours_set = set()

    for _, r in df.iterrows():
        org_data = {col: r[col] for col in org_cols}
        lst = parse_breakdown(r.get("buildpack_component_breakdown_json", "[]"))

        for e in lst:
            if not isinstance(e, dict):
                continue
            ctype = e.get("componentType")
            if not isinstance(ctype, str):
                continue

            buildpack = e.get("buildpack") or "UNKNOWN"
            count = e.get("count", 1)

            bp_rows.append({
                **org_data,
                "componentTypeName": ctype,
                "buildpack": buildpack,
                "bp_count": count,
            })
            flavours_set.add(buildpack)

    # Build a grouped breakdown DF (can be empty if no buildpacks at all)
    if bp_rows:
        df_bp = pd.DataFrame(bp_rows)
        df_bp_group = df_bp.groupby(org_cols + ["componentTypeName", "buildpack"],
                                    as_index=False)["bp_count"].sum()
        # Pivot buildpack flavours into columns
        index_cols = org_cols + ["componentTypeName"]
        bp_pivot = df_bp_group.pivot_table(
            index=index_cols,
            columns="buildpack",
            values="bp_count",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
    else:
        bp_pivot = None
        flavours_set = set()

    # ---------------------------------------------------------
    # 4) Merge base table with breakdown (left join!)
    # ---------------------------------------------------------
    index_cols = org_cols + ["componentTypeName"]
    merged = df_types.merge(bp_pivot, on=index_cols, how="left")

    # ---------------------------------------------------------
    # 5) Flavour columns (languages)
    # ---------------------------------------------------------
    # Flavours from breakdown + ensure UNKNOWN exists
    flavours_set.add("UNKNOWN")
    flavours = sorted(flavours_set)

    # Ensure all flavour columns exist and NaNs -> 0
    for fl in flavours:
        if fl not in merged.columns:
            merged[fl] = 0
        else:
            merged[fl] = merged[fl].fillna(0)

    # ---------------------------------------------------------
    # 6) Distribute counts:
    #    - Non-buildpack types => all to UNKNOWN
    #    - Buildpack* types => from breakdown, remainder to UNKNOWN
    # ---------------------------------------------------------
    # For non-buildpack component types: put full component_count into UNKNOWN
    mask_non_bp = ~merged["componentTypeName"].str.startswith("buildpack", na=False)
    merged.loc[mask_non_bp, "UNKNOWN"] = (
        merged.loc[mask_non_bp, "UNKNOWN"] + merged.loc[mask_non_bp, "component_count"]
    )

    # For buildpack types:
    mask_bp = merged["componentTypeName"].str.startswith("buildpack", na=False)

    # Sum of flavours from breakdown (including UNKNOWN if it was in the breakdown)
    flavour_cols = flavours
    sum_flavours = merged[flavour_cols].sum(axis=1)

    # Where total from flavours < component_count, put remainder into UNKNOWN
    # (this also covers the case where there is no breakdown at all)
    remainder_mask = mask_bp & (sum_flavours < merged["component_count"])
    merged.loc[remainder_mask, "UNKNOWN"] = (
        merged.loc[remainder_mask, "UNKNOWN"]
        + (merged.loc[remainder_mask, "component_count"] - sum_flavours[remainder_mask])
    )

    # Recompute sum_flavours after adding remainders
    merged["componentTypeCount"] = merged[flavour_cols].sum(axis=1)

    # Sanity: total componentTypeCount should equal original component_count
    # (not strictly required, but good to know it's consistent)
    # print("Total original component_count:", merged["component_count"].sum())
    # print("Total redistributed componentTypeCount:", merged["componentTypeCount"].sum())

    # ---------------------------------------------------------
    # 7) Final column order & save
    # ---------------------------------------------------------
    final_cols = org_cols + ["componentTypeCount", "componentTypeName"] + flavours
    result = merged[final_cols]

    out_file = os.path.join(DATA_DIR, "buildpack_by_org_and_type.csv")
    result.to_csv(out_file, index=False)

    print(f"✔ Input rows (orgs): {len(df)}")
    print(f"✔ Org+componentType rows (output): {len(result)}")
    print(f"✔ Output written to: {out_file}")
    print(f"✔ Flavour columns: {', '.join(flavours)}")
    print("Done.")


if __name__ == "__main__":
    main()
