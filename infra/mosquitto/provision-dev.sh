#!/usr/bin/env bash
# Provision the development-only Mosquitto password file (C-W02-01).
#
# The output file infra/mosquitto/passwd is git-ignored and never
# committed. This script is the single reproducible provisioning step:
# it uses the repository-pinned Mosquitto image's own `mosquitto_passwd`
# utility, so hashes are always compatible with the deployed broker.
#
# Usage:
#   MOSQUITTO_DEVICE_PASSWORD=... MOSQUITTO_BACKEND_PASSWORD=... \
#     infra/mosquitto/provision-dev.sh
#
# Defaults are development-only placeholders. For any shared/demo use,
# export real per-checkout passwords; they stay in the environment and
# the generated file, never in Git, shell history files, or logs
# (values are never echoed).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${MOSQUITTO_IMAGE:-eclipse-mosquitto:2.1.2-alpine}"
DEVICE_USER="${MOSQUITTO_DEVICE_USER:-device-coldguard-001}"
BACKEND_USER="${MOSQUITTO_BACKEND_USER:-backend-ingest}"
DEVICE_PASSWORD="${MOSQUITTO_DEVICE_PASSWORD:-device_dev_only}"
BACKEND_PASSWORD="${MOSQUITTO_BACKEND_PASSWORD:-backend_dev_only}"
OUT="${DIR}/passwd"

if [ "${DEVICE_PASSWORD}" = "device_dev_only" ] || [ "${BACKEND_PASSWORD}" = "backend_dev_only" ]; then
  echo "provision-dev.sh: using development placeholder passwords;" \
    "export MOSQUITTO_DEVICE_PASSWORD / MOSQUITTO_BACKEND_PASSWORD for non-local use" >&2
fi

rm -f "${OUT}.tmp"
# Run as the invoking user so the output stays user-owned
# (re-provisionable and removable without root).
docker run --rm --user "$(id -u):$(id -g)" \
  -e MOSQUITTO_DEVICE_USER="${DEVICE_USER}" \
  -e MOSQUITTO_BACKEND_USER="${BACKEND_USER}" \
  -e MOSQUITTO_DEVICE_PASSWORD="${DEVICE_PASSWORD}" \
  -e MOSQUITTO_BACKEND_PASSWORD="${BACKEND_PASSWORD}" \
  -v "${DIR}:/out:z" \
  "${IMAGE}" sh -c \
  'mosquitto_passwd -c -b /out/passwd.tmp "$MOSQUITTO_DEVICE_USER" "$MOSQUITTO_DEVICE_PASSWORD" \
   && mosquitto_passwd -b /out/passwd.tmp "$MOSQUITTO_BACKEND_USER" "$MOSQUITTO_BACKEND_PASSWORD"'
mv "${OUT}.tmp" "${OUT}"
# The broker drops privileges to an unprivileged `mosquitto` uid inside
# its container, so the file must stay readable by other uids. This is
# safe here: the file holds only salted password hashes (never the
# passwords), uses development-only credentials, is served on 127.0.0.1
# only, and is git-ignored / never committed.
chmod 644 "${OUT}"
echo "provision-dev.sh: wrote ${OUT} (mode 644 salted hashes, git-ignored)"
