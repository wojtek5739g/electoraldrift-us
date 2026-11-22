#!/usr/bin/env bash
# Redeploy the latest commit on the VM: ./deploy/deploy_update.sh <public_ip> [branch]
set -euo pipefail
IP="${1:?usage: deploy_update.sh <public_ip> [branch]}"
BRANCH="${2:-main}"
ssh "ubuntu@${IP}" "cd /opt/electoraldrift && git fetch origin && git checkout ${BRANCH} && git pull --ff-only origin ${BRANCH} && docker compose up -d --build && docker compose ps"
