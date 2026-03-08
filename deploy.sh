#!/usr/bin/env bash
# deploy.sh — Build, push, and deploy the IGA Browser Agent
# Usage: ./deploy.sh [dev|prod]
set -euo pipefail

ENV="${1:-dev}"
RG="rg-iga-agent-${ENV}"
LOCATION="eastus2"

echo "=== IGA Browser Agent — Deploy to ${ENV} ==="

# Step 1: Create resource group if it doesn't exist
echo "[1/4] Ensuring resource group ${RG}..."
az group create --name "$RG" --location "$LOCATION" --output none 2>/dev/null || true

# Step 2: Deploy infrastructure
echo "[2/4] Deploying infrastructure (Bicep)..."
DEPLOY_OUTPUT=$(az deployment group create \
  --resource-group "$RG" \
  --template-file infrastructure/main.bicep \
  --parameters "infrastructure/parameters/${ENV}.bicepparam" \
  --query 'properties.outputs' \
  --output json)

ACR_LOGIN_SERVER=$(echo "$DEPLOY_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['acrLoginServer']['value'])")
APP_URL=$(echo "$DEPLOY_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['containerAppUrl']['value'])")
ACR_NAME=$(echo "$ACR_LOGIN_SERVER" | cut -d. -f1)

echo "  ACR: ${ACR_LOGIN_SERVER}"
echo "  App URL: ${APP_URL}"

# Step 3: Build and push Docker image to ACR
echo "[3/4] Building and pushing Docker image..."
az acr build \
  --registry "$ACR_NAME" \
  --image "iga-agent:latest" \
  --image "iga-agent:$(date +%Y%m%d%H%M%S)" \
  .

# Step 4: Update container app to pull latest image
echo "[4/4] Updating Container App..."
az containerapp update \
  --name "aca-iga-agent-${ENV}" \
  --resource-group "$RG" \
  --image "${ACR_LOGIN_SERVER}/iga-agent:latest"

echo ""
echo "=== Deployment complete ==="
echo "API URL: ${APP_URL}"
echo "Health:  ${APP_URL}/health"
echo "Agents:  ${APP_URL}/api/agents"
echo ""
echo "Test with:"
echo "  curl ${APP_URL}/health"
echo "  curl -X POST ${APP_URL}/api/tasks -H 'Content-Type: application/json' -d '{\"agent\":\"greenfield-provision\",\"inputs\":{\"full_name\":\"Test User\",\"email\":\"test@example.com\",\"department\":\"IT\",\"title\":\"Tester\",\"role\":\"user\"}}'"
