#!/bin/bash

set -e

ADMIN_KEY_VAULT_NAME='kv-asgr-admin-pr-eus2-01'
SQL_SERVER_NAME='sql-asgardeo-main-prod-eastus2-001.database.windows.net'
SHARED_USER_DATABASE_NAME='sqldb-asgardeo-is-user-prod'

CSV_FILE="${1:-organization-names.csv}"

if [[ ! -f "$CSV_FILE" ]]; then
    echo "Error: CSV file '$CSV_FILE' not found!"
    exit 1
fi

echo "Fetching credentials from Azure Key Vault..."
SQL_SERVER_DATABASE_USERNAME=$(az keyvault secret show --name USER-STORE-READ-ONLY-USER-USERNAME --vault-name ${ADMIN_KEY_VAULT_NAME} --query value -o tsv)
SQL_SERVER_DATABASE_PASSWORD=$(az keyvault secret show --name USER-STORE-READ-ONLY-USER-PASSWORD --vault-name ${ADMIN_KEY_VAULT_NAME} --query value -o tsv)

OUTPUT_DIR="output"
mkdir -p "$OUTPUT_DIR"

COMBINED_OUTPUT="$OUTPUT_DIR/all-org-owners.csv"
echo "organization_name,email" > "$COMBINED_OUTPUT"

total_orgs=$(tail -n +2 "$CSV_FILE" | wc -l | tr -d ' ')
current=0

echo "Processing $total_orgs organizations from $CSV_FILE..."
echo "----------------------------------------"

while IFS=, read -r domain || [[ -n "$domain" ]]; do
    domain=$(echo "$domain" | xargs)
    
    [[ -z "$domain" ]] && continue
    
    current=$((current + 1))
    echo "[$current/$total_orgs] Processing: $domain"
    
    # Query and capture output directly
    query_output=$(sqlcmd -S "$SQL_SERVER_NAME" \
           -U "$SQL_SERVER_DATABASE_USERNAME" \
           -P "$SQL_SERVER_DATABASE_PASSWORD" \
           -d "$SHARED_USER_DATABASE_NAME" \
           -Q "SELECT UM_EMAIL FROM UM_TENANT WHERE UM_DOMAIN_NAME='$domain';" \
           -w15000 2>/dev/null || true)
    
    # Skip header (UM_EMAIL), dashes line, empty lines, and "rows affected" line; get the email
    email=$(echo "$query_output" | tr -d '\r' | grep -v '^UM_EMAIL' | grep -v '^---' | grep -v 'rows affected' | grep -v '^$' | head -n 1 | xargs)
    
    if [[ -z "$email" ]]; then
        email="NOT_FOUND"
    fi
    
    echo "$domain,$email" >> "$COMBINED_OUTPUT"
    
done < <(tail -n +2 "$CSV_FILE")

echo "----------------------------------------"
echo "Processing complete!"

