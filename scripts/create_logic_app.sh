#!/bin/bash
# Create Azure Logic App to check trucker balances 5 times a day.
# Usage: ./scripts/create_logic_app.sh
#
# Prerequisites:
#   - az login (Azure CLI authenticated)
#   - Function app "nhutin-trucker-api" deployed with the alerts endpoint
#
# The Logic App calls GET /api/alerts/check-balances every ~5 hours.
# Schedule: 06:00, 09:00, 12:00, 15:00, 18:00 (UTC+7 = Asia/Ho_Chi_Minh)
set -euo pipefail

RESOURCE_GROUP="nhutin-prod"
LOCATION="southeastasia"
LOGIC_APP_NAME="nhutin-balance-alert"
FUNCTION_APP_URL="https://nhutin-trucker-api.azurewebsites.net/api/alerts/check-balances"

# ── Function key for auth ───────────────────────────────────────────────
echo "=== Fetching function key ==="
FUNCTION_KEY=$(az functionapp keys list \
  --name nhutin-trucker-api \
  --resource-group "$RESOURCE_GROUP" \
  --query "functionKeys.default" -o tsv 2>/dev/null || true)

if [ -z "$FUNCTION_KEY" ]; then
  echo "WARNING: Could not auto-fetch function key."
  echo "You can set it manually after creation in the Logic App designer."
  echo "The key from the user: pass it via Azure portal or set FUNCTION_KEY env var."
  CALL_URL="$FUNCTION_APP_URL"
else
  CALL_URL="${FUNCTION_APP_URL}?code=${FUNCTION_KEY}"
fi

echo ""
echo "=== Creating Logic App: $LOGIC_APP_NAME ==="

# Logic App workflow definition — recurrence trigger + HTTP action
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
          "uri": "PLACEHOLDER_URL",
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

# Inject the actual URL into the definition
DEFINITION=$(echo "$DEFINITION" | sed "s|PLACEHOLDER_URL|${CALL_URL}|g")

# Write temp file (Logic App CLI needs a file path)
TMPFILE=$(mktemp /tmp/logic-app-def.XXXXXX.json)
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
echo "Endpoint: $FUNCTION_APP_URL"
echo ""
echo "=== Next steps ==="
echo "1. Set these env vars on the function app (nhutin-trucker-api):"
echo "   GMAIL_ADDRESS         = your Gmail address"
echo "   GMAIL_APP_PASSWORD    = your Google app password"
echo "   ALERT_RECIPIENTS      = comma-separated emails (you + client)"
echo "   LOW_BALANCE_THRESHOLD = 500000 (default, already set in code)"
echo ""
echo "   az functionapp config appsettings set \\"
echo "     --name nhutin-trucker-api \\"
echo "     --resource-group $RESOURCE_GROUP \\"
echo "     --settings \\"
echo "       GMAIL_ADDRESS=your@gmail.com \\"
echo "       GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx \\"
echo "       ALERT_RECIPIENTS=you@gmail.com,client@gmail.com"
echo ""
echo "2. Deploy the function app (push to main branch for GitHub Actions)"
echo "3. Test: curl '${CALL_URL}'"
