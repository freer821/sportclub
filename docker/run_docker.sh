#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="basketball-club-dev"
CONTAINER_NAME="basketball-club-dev"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker build -f "${PROJECT_ROOT}/docker/Dockerfile" -t "${IMAGE_NAME}" "${PROJECT_ROOT}"

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

docker run -it --rm \
  --name "${CONTAINER_NAME}" \
  -p 8000:8000 \
  -v "${PROJECT_ROOT}:/app" \
  -e DJANGO_SETTINGS_MODULE=config.settings \
  -e DB_NAME="${DB_NAME:-sport_club}" \
  -e DB_USER="${DB_USER:-root}" \
  -e DB_PASSWORD="${DB_PASSWORD:-Qwer1234@}" \
  -e DB_HOST="${DB_HOST:-host.docker.internal}" \
  -e DB_PORT="${DB_PORT:-5432}" \
  "${IMAGE_NAME}"
