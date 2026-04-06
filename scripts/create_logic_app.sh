#!/bin/bash
# Create/update Azure Logic App to check trucker balances AND contract completion 5 times a day.
# Usage: ./scripts/create_logic_app.sh
#
# Prerequisites:
#   - az login (Azure CLI authenticated)
#   - Function app "nhutin-trucker-api" deployed with the alerts endpoints
#
# The Logic App calls both:
#   - GET /api/alerts/check-balances   (low trucker balance → email)
#   - GET /api/alerts/check-contracts  (contract ≥90% complete → email)
#
# Schedule: 06:00, 09:00, 12:00, 15:00, 18:00 (UTC+7 = Asia/Ho_Chi_Minh)
set -euo pipefail

RESOURCE_GROUP="nhutin-prod"
LOCATION="southeastasia"
LOGIC_APP_NAME="nhutin-balance-alert"
BASE_URL="https://nhutin-trucker-api.azurewebsites.net/api/alerts"

# ── Function key for auth ───────────────────────────────────────────────
echo "=== Fetching function key ==="
FUNCTION_KEY=$(az functionapp keys list \
  --name nhutin-trucker-api \
  --resource-group "$RESOURCE_GROUP" \
  --query "functionKeys.default" -o tsv 2>/dev/null || true)

if [ -z "$FUNCTION_KEY" ]; then
  echo "WARNING: Could not auto-fetch function key."
  echo "You can set it manually after creation in the Logic App designer."
  BALANCE_URL="${BASE_URL}/check-balances"
  CONTRACT_URL="${BASE_URL}/check-contracts"
else
  BALANCE_URL="${BASE_URL}/check-balances?code=${FUNCTION_KEY}"
  CONTRACT_URL="${BASE_URL}/check-contracts?code=${FUNCTION_KEY}"
fi

echo ""
echo "=== Creating Logic App: $LOGIC_APP_NAME ==="

# Logic App workflow definition — recurrence trigger + two HTTP actions (parallel)
DEFINITION=$(cat <<'DEFEOF'
{
  "definition": {
    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "contentVersion": "1.0.0.0",
    "triggers": {
      "Recurrence": {
        "type": "Recurrence",
        "recurrence": {
          "frequency": "Day",
          "interval": 1,
          "timeZone": "SE Asia Standard Time",
          "schedule": {
            "hours": [6, 9, 12, 15, 18]
          }
        }
      }
    },
    "actions": {
      "Check_Balances": {
        "type": "Http",
        "inputs": {
          "method": "GET",
          "uri": "PLACEHOLDER_BALANCE_URL",
          "headers": {
            "Accept": "application/json"
          }
        },
        "runAfter": {}
      },
      "Check_Contracts": {
        "type": "Http",
        "inputs": {
          "method": "GET",
          "uri": "PLACEHOLDER_CONTRACT_URL",
          "headers": {
            "Accept": "application/json"
          }
        },
        "runAfter": {}
      }
    },
    "outputs": {}
  },
  "parameters": {}
}
DEFEOF
)

# Inject the actual URLs into the definition
DEFINITION=$(echo "$DEFINITION" | sed "s|PLACEHOLDER_BALANCE_URL|${BALANCE_URL}|g")
DEFINITION=$(echo "$DEFINITION" | sed "s|PLACEHOLDER_CONTRACT_URL|${CONTRACT_URL}|g")

# Write temp file (Logic App CLI needs a file path)
TMPFILE=$(mktemp /tmp/logic-app-def-XXXXXX.json)
echo "$DEFINITION" > "$TMPFILE"

az logic workflow create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$LOGIC_APP_NAME" \
  --location "$LOCATION" \
  --definition "$TMPFILE" \
  --state "Enabled" \
  --output table

rm -f "$TMPFILE"

echo ""
echo "=== Logic App created ==="
echo "Name: $LOGIC_APP_NAME"
echo "Schedule: 06:00, 09:00, 12:00, 15:00, 18:00 (Vietnam time)"
echo "Actions:"
echo "  1. Check_Balances  → ${BASE_URL}/check-balances"
echo "  2. Check_Contracts → ${BASE_URL}/check-contracts"
echo ""
echo "Both actions run in parallel on each trigger."
echo ""
echo "=== Configuration ==="
echo "  LOW_BALANCE_THRESHOLD    = 500000 VND (default)"
echo "  CONTRACT_ALERT_THRESHOLD = 90% (default)"
echo "  GMAIL_ADDRESS            = sender Gmail"
echo "  GMAIL_APP_PASSWORD       = Google app password"
echo "  ALERT_RECIPIENTS         = comma-separated emails"
