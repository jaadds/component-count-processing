#!/usr/bin/env python3
import os
import pandas as pd
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

def combine_csv_files():
    try:
        # Read the buildpack file
        print("Reading buildpack_by_org_and_type.csv...")
        buildpack_df = pd.read_csv(os.path.join(DATA_DIR, 'buildpack_by_org_and_type.csv'))
        print(f"Loaded {len(buildpack_df)} rows from buildpack file")

        # Read the subscription status file
        print("Reading Prod Nodes - 04_12 - Component Count.csv...")
        subscription_df = pd.read_csv(os.path.join(DATA_DIR, 'Prod Nodes - 04_12 - Component Count.csv'))
        print(f"Loaded {len(subscription_df)} rows from subscription file")

        # Merge the dataframes on org_uuid (from buildpack) = organization_id (from subscription)
        print("\nMerging data on organization_id...")
        combined_df = buildpack_df.merge(
            subscription_df,
            left_on='org_uuid',
            right_on='organization_id',
            how='left'
        )

        print(f"Combined data has {len(combined_df)} rows")

        # Reorder columns to have subscription info near the beginning
        # Get all column names
        all_columns = combined_df.columns.tolist()

        # Define priority columns from subscription file
        priority_cols = ['org_uuid', 'handle', 'organization_id', 'org-handle',
                        'Paying', 'Classification', 'Owner', 'podCount', 'componentCount']

        # Create ordered column list
        ordered_cols = []
        for col in priority_cols:
            if col in all_columns:
                ordered_cols.append(col)

        # Add remaining columns
        for col in all_columns:
            if col not in ordered_cols:
                ordered_cols.append(col)

        combined_df = combined_df[ordered_cols]

        # Save to new CSV file
        output_file = os.path.join(DATA_DIR, 'combined_components_and_subscription.csv')
        print(f"\nSaving combined data to {output_file}...")
        combined_df.to_csv(output_file, index=False)

        print(f"\nSuccess! Created {output_file}")
        print(f"Total rows: {len(combined_df)}")
        print(f"Total columns: {len(combined_df.columns)}")

        # Show some statistics
        print("\n=== Data Summary ===")
        print(f"Organizations with subscription data: {combined_df['Paying'].notna().sum()}")
        print(f"Organizations without subscription data: {combined_df['Paying'].isna().sum()}")

        if combined_df['Paying'].notna().sum() > 0:
            print(f"\nPaying status breakdown:")
            print(combined_df['Paying'].value_counts(dropna=False))

        # Show first few rows
        print("\n=== First 5 rows preview ===")
        print(combined_df.head().to_string())

    except FileNotFoundError as e:
        print(f"Error: Could not find file - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    combine_csv_files()
