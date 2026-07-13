#!/usr/bin/env python3
import pandas as pd
import ast
import sys
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

# -------------------------------------------------------------
# Helper: parse JSON-ish strings safely
# -------------------------------------------------------------
def parse_breakdown(value):
    if pd.isna(value) or value in ("[]", "{}", "", " "):
        return []
    value = str(value).strip()
    try:
        return ast.literal_eval(value)
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

    # 1) Load CSV
    df = pd.read_csv(input_csv)

    # 2) Parse buildpack breakdown JSON-like column
    df["breakdown_list"] = df["buildpack_component_breakdown_json"].apply(parse_breakdown)

    # 3) Explode: each buildpack entry becomes its own row
    df_exp = df.explode("breakdown_list", ignore_index=True)

    # Keep only rows where breakdown_list is a dict (i.e., a valid entry)
    df_exp = df_exp[df_exp["breakdown_list"].apply(lambda x: isinstance(x, dict))]

    if df_exp.empty:
        print("No buildpack data found in this CSV.")
        sys.exit(0)

    # 4) Extract fields from each breakdown entry
    df_exp["componentType"] = df_exp["breakdown_list"].apply(lambda d: d.get("componentType"))
    df_exp["buildpack"] = df_exp["breakdown_list"].apply(lambda d: d.get("buildpack"))
    df_exp["bp_count"] = df_exp["breakdown_list"].apply(lambda d: d.get("count", 1))

    # 5) Filter ONLY componentTypes that start with 'buildpack'
    df_bp = df_exp[df_exp["componentType"].str.startswith("buildpack", na=False)]

    if df_bp.empty:
        print("No buildpack componentTypes found.")
        sys.exit(0)

    # 6) Pivot so buildpack flavours become columns (one row per org + componentType)
    index_cols = [
        "org_uuid",
        "org_numeric_id",
        "handle",
        "origin_cloud",
        "choreo-subscription-paid",
        "devant-subscription-paid",
        "bijira-subscription-paid",
        "componentType",
    ]

    pivot = (
        df_bp
        .pivot_table(
            index=index_cols,
            columns="buildpack",
            values="bp_count",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )

    # 7) Compute buildpack_component_count = sum of all flavour columns
    flavour_cols = [c for c in pivot.columns if c not in index_cols]
    pivot["buildpack_component_count"] = pivot[flavour_cols].sum(axis=1)

    # 8) Final column order
    final_cols = [
        "org_uuid",
        "org_numeric_id",
        "handle",
        "origin_cloud",
        "choreo-subscription-paid",
        "devant-subscription-paid",
        "bijira-subscription-paid",
        "buildpack_component_count",
        "componentType",
    ] + flavour_cols

    result = pivot[final_cols].rename(columns={"componentType": "buildpackComponentType"})

    # 9) Save output
    out_file = os.path.join(DATA_DIR, "buildpack_by_org_and_type.csv")
    result.to_csv(out_file, index=False)

    print(f"✔ Output written to: {out_file}")
    print(f"✔ Total rows: {len(result)}")
    print("Done.")


if __name__ == "__main__":
    main()
