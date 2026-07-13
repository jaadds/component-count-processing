#!/bin/bash
set -e
set -o pipefail

env=$1

if [ $env == "prod-us" ]; then
    echo "exporting prod-us..."
    export ADMIN_KEY_VAULT_NAME='kv-asgr-admin-pr-eus2-01'
    export SQL_SERVER_NAME='sql-asgardeo-main-prod-eastus2-001.database.windows.net'
    export SHARED_USER_DATABASE_NAME='sqldb-asgardeo-is-user-prod'
    echo "exporting completed prod-us!"
elif [ $env == "prod-eu" ]; then
    echo "exporting prod-eu..."
    export ADMIN_KEY_VAULT_NAME='kv-asgr-admin-eupr-ne-02'
    export SQL_SERVER_NAME='sql-asgardeo-main-eupr-northeurope-001.database.windows.net'
    export SHARED_USER_DATABASE_NAME='sqldb-asgardeo-is-user-eupr'
    echo "exporting completed prod-eu!"
else
  exit 1;
fi

SQL_SERVER_DATABASE_USERNAME=$(az keyvault secret show --name USER-STORE-READ-ONLY-USER-USERNAME --vault-name ${ADMIN_KEY_VAULT_NAME} --query value -o tsv)
SQL_SERVER_DATABASE_PASSWORD=$(az keyvault secret show --name USER-STORE-READ-ONLY-USER-PASSWORD --vault-name ${ADMIN_KEY_VAULT_NAME} --query value -o tsv)

OUTPUT_FILE="emails.csv"

# Ensure the output file exists and is empty initially
> $OUTPUT_FILE

# Since we have a large number of UUIDs, let's process them in chunks
CHUNK_SIZE=20
total_lines=$(wc -l < uuids.csv)
current_line=0

while [ $current_line -lt $total_lines ]; do
    # Get next chunk of UUIDs
    uuids_list=$(tail -n +$((current_line + 1)) uuids.csv | head -n $CHUNK_SIZE | tr '\n' ',' | sed 's/,$//')
    
    # Format UUIDs for SQL IN clause
    formatted_uuids=$(echo $uuids_list | sed "s/,/\',\'/g")
    formatted_uuids="'$formatted_uuids'"

    # Execute SQL query for this chunk
    sqlcmd -S "$SQL_SERVER_NAME" \
           -U "$SQL_SERVER_DATABASE_USERNAME" \
           -P "$SQL_SERVER_DATABASE_PASSWORD" \
           -d "$SHARED_USER_DATABASE_NAME" \
           -Q "SET NOCOUNT ON; SELECT UM_ORG_UUID, UM_TENANT_UUID, UM_DOMAIN_NAME, UM_EMAIL FROM UM_TENANT WHERE UM_ORG_UUID IN ($formatted_uuids);" \
           -o "temp.csv" \
           -s"," \
           -w15000 \
           -y 0 \
           < /dev/null

    # Append results to main output file (skip header for all but first chunk)
    if [ $current_line -eq 0 ]; then
        cat temp.csv >> "$OUTPUT_FILE"
    else
        tail -n +2 temp.csv >> "$OUTPUT_FILE"
    fi

    rm temp.csv
    current_line=$((current_line + CHUNK_SIZE))
    echo "Processed $current_line out of $total_lines UUIDs"
done

echo "Query completed. Results saved in $OUTPUT_FILE"