#!/usr/bin/env bash
set -euo pipefail

SERVICIOS=(
  "bff:8000"
  "crud:8001"
  "process:8002"
  "inference:8003"
  "geo:8004"
)

errores=0

for servicio in "${SERVICIOS[@]}"; do
  nombre="${servicio%%:*}"
  puerto="${servicio##*:}"
  if curl -s --max-time 5 "http://localhost:${puerto}/health" > /dev/null 2>&1; then
    echo "OK: ${nombre} (${puerto})"
  else
    echo "ERROR: ${nombre} (${puerto}) no responde" >&2
    errores=$((errores + 1))
  fi
done

if [ ${errores} -gt 0 ]; then
  echo "${errores} servicio(s) no responden" >&2
  exit 1
fi

echo "Todos los servicios responden OK"
