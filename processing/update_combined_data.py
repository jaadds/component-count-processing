#!/usr/bin/env python3
import os
import pandas as pd
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

def update_combined_data():
    try:
        # Read the current combined file
        print("Reading current combined_components_and_subscription.csv...")
        combined_df = pd.read_csv(os.path.join(DATA_DIR, 'combined_components_and_subscription.csv'))
        print(f"Loaded {len(combined_df)} rows from combined file")

        # Count how many rows have missing subscription data before update
        missing_before = combined_df['organization_id'].isna().sum()
        print(f"Rows with missing subscription data: {missing_before}")

        # Read the full subscription list
        print("\nReading full-subscription-list.csv...")
        full_sub_df = pd.read_csv(os.path.join(DATA_DIR, 'full-subscription-list.csv'))
        print(f"Loaded {len(full_sub_df)} rows from full subscription list")

        # Rename columns in full_sub_df to match the combined file structure
        full_sub_df = full_sub_df.rename(columns={
            'Org-id': 'organization_id',
            'Org Handle': 'org-handle',
            'Owner Email': 'Owner'
        })

        # Keep only relevant columns from full subscription list
        full_sub_columns = ['organization_id', 'org-handle', 'Owner', 'Classification']
        full_sub_df = full_sub_df[full_sub_columns]

        # For rows where organization_id is missing, try to merge with full subscription list
        print("\nFilling missing subscription data...")

        # Create a mask for rows with missing subscription data
        missing_mask = combined_df['organization_id'].isna()

        # For rows with missing data, perform a left merge with full subscription list
        # We'll merge on org_uuid from combined_df to organization_id from full_sub_df
        rows_with_missing = combined_df[missing_mask].copy()
        rows_without_missing = combined_df[~missing_mask].copy()

        print(f"Rows to update: {len(rows_with_missing)}")
        print(f"Rows to keep unchanged: {len(rows_without_missing)}")

        # Merge missing rows with full subscription data
        updated_rows = rows_with_missing.merge(
            full_sub_df,
            left_on='org_uuid',
            right_on='organization_id',
            how='left',
            suffixes=('', '_new')
        )

        # Update only the columns that were missing
        for col in ['organization_id', 'org-handle', 'Owner', 'Classification']:
            if col + '_new' in updated_rows.columns:
                # Fill missing values with new data
                updated_rows[col] = updated_rows[col + '_new']
                # Drop the temporary column
                updated_rows = updated_rows.drop(columns=[col + '_new'])

        # Combine the unchanged rows with the updated rows
        final_df = pd.concat([rows_without_missing, updated_rows], ignore_index=True)

        # Sort by org_uuid to maintain order
        final_df = final_df.sort_index()

        # Count how many rows have missing subscription data after update
        missing_after = final_df['organization_id'].isna().sum()
        filled_count = missing_before - missing_after

        print(f"\nRows filled with new subscription data: {filled_count}")
        print(f"Rows still missing subscription data: {missing_after}")

        # Save to the same file (overwrite)
        output_file = os.path.join(DATA_DIR, 'combined_components_and_subscription.csv')
        print(f"\nUpdating {output_file}...")
        final_df.to_csv(output_file, index=False)

        print(f"\nSuccess! Updated {output_file}")
        print(f"Total rows: {len(final_df)}")
        print(f"Total columns: {len(final_df.columns)}")

        # Show statistics
        print("\n=== Data Summary ===")
        print(f"Organizations with subscription data: {final_df['organization_id'].notna().sum()}")
        print(f"Organizations without subscription data: {final_df['organization_id'].isna().sum()}")

        if final_df['Classification'].notna().sum() > 0:
            print(f"\nClassification breakdown:")
            print(final_df['Classification'].value_counts(dropna=False))

        # Show sample of newly filled data
        newly_filled = final_df[
            (final_df['org_uuid'].isin(rows_with_missing['org_uuid'])) &
            (final_df['organization_id'].notna())
        ]

        if len(newly_filled) > 0:
            print(f"\n=== Sample of newly filled data (first 5) ===")
            cols_to_show = ['org_uuid', 'handle', 'organization_id', 'org-handle', 'Owner', 'Classification']
            print(newly_filled[cols_to_show].head().to_string())

    except FileNotFoundError as e:
        print(f"Error: Could not find file - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    update_combined_data()
