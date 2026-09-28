#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/azureuser/pmu-structured-extraction"
ENV_FILE="${REPO_DIR}/.env"

if [ ! -d "${REPO_DIR}" ]; then
  echo "ERROR: no existe el repo en ${REPO_DIR}" >&2
  exit 1
fi

az login --identity

version=$(az ml model list --name sirena-extractor --resource-group rg-sirena-mp3 --workspace-name mlw-sirena --query "max_by(@, &to_number(version)).version" -o tsv)
if [ -z "${version}" ]; then
  echo "ERROR: no se encontro sirena-extractor en el registro" >&2
  exit 1
fi

modelo=$(az ml model show --name sirena-extractor --version "${version}" --resource-group rg-sirena-mp3 --workspace-name mlw-sirena --query "tags.modelo" -o tsv)
if [ -z "${modelo}" ]; then
  echo "ERROR: no se pudo leer tags.modelo de sirena-extractor:${version}" >&2
  exit 1
fi

cd "${REPO_DIR}"

if [ -f "${ENV_FILE}" ]; then
  sed -i "s|^INFERENCE_MODELO=.*|INFERENCE_MODELO=${modelo}|" "${ENV_FILE}"
else
  echo "INFERENCE_MODELO=${modelo}" > "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
fi

docker compose up -d inference

echo "Inference usa ${modelo} (sirena-extractor:${version})"
