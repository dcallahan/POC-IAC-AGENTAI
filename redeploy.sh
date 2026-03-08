#!/usr/bin/env bash
# redeploy.sh — Rebuild and redeploy after code changes (no infra changes)
# Usage: ./redeploy.sh [dev|prod]
set -euo pipefail

ENV="${1:-dev}"
RG="rg-iga-agent-${ENV}"
ACR_NAME="acrigaagent${ENV}"
ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"
TAG="$(date +%Y%m%d%H%M%S)"

echo "=== IGA Browser Agent — Redeploy (${ENV}) ==="

# Build and push new image
echo "[1/2] Building image (tag: ${TAG})..."
az acr build \
  --registry "$ACR_NAME" \
  --image "iga-agent:latest" \
  --image "iga-agent:${TAG}" \
  .

# Update container app
echo "[2/2] Updating Container App..."
az containerapp update \
  --name "aca-iga-agent-${ENV}" \
  --resource-group "$RG" \
  --image "${ACR_LOGIN_SERVER}/iga-agent:latest"

FQDN=$(az containerapp show \
  --name "aca-iga-agent-${ENV}" \
  --resource-group "$RG" \
  --query 'properties.configuration.ingress.fqdn' \
  --output tsv)

echo ""
echo "=== Redeployed ==="
echo "API: https://${FQDN}"
echo "Tag: ${TAG}"
