#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/azureuser/pmu-structured-extraction"
ENV_FILE="${REPO_DIR}/.env"
KEY_VAULT_NAME="mlwsirenkeyvault18607254"

if [ ! -d "${REPO_DIR}" ]; then
  echo "ERROR: no existe el repo en ${REPO_DIR}" >&2
  exit 1
fi

az login --identity

groq_key=$(az keyvault secret show --vault-name "${KEY_VAULT_NAME}" --name groq-api-key --query "value" -o tsv 2>/dev/null)
if [ -z "${groq_key}" ]; then
  echo "ERROR: no se pudo leer groq-api-key del Key Vault" >&2
  exit 1
fi

if ! echo "${groq_key}" | grep -q "^gsk_"; then
  echo "ERROR: groq-api-key no empieza por gsk_" >&2
  exit 1
fi

telegram_token=$(az keyvault secret show --vault-name "${KEY_VAULT_NAME}" --name telegram-bot-token --query "value" -o tsv 2>/dev/null)
if [ -z "${telegram_token}" ]; then
  echo "ERROR: no se pudo leer telegram-bot-token del Key Vault" >&2
  exit 1
fi

if [ -f "${ENV_FILE}" ]; then
  inference_modelo=$(grep "^INFERENCE_MODELO=" "${ENV_FILE}" | cut -d= -f2)
else
  inference_modelo=""
fi

if [ -z "${inference_modelo}" ]; then
  inference_modelo="openai/gpt-oss-20b"
fi

cat > "${ENV_FILE}" <<EOF
GROQ_API_KEY=${groq_key}
TELEGRAM_BOT_TOKEN=${telegram_token}
INFERENCE_MODELO=${inference_modelo}
EOF

chmod 600 "${ENV_FILE}"

echo ".env creado en ${ENV_FILE} con permisos 600"
