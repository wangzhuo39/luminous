#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this rollback as root." >&2
  exit 1
fi
if [[ ! -L /opt/luminous/previous ]]; then
  echo "No previous release is recorded." >&2
  exit 1
fi

previous="$(readlink -f /opt/luminous/previous)"
current="$(readlink -f /opt/luminous/current)"
[[ -d "$previous" && "$previous" == /opt/luminous/releases/* ]] || { echo "Invalid previous release." >&2; exit 1; }
ln -sfn "$previous" /opt/luminous/.current-rollback
mv -Tf /opt/luminous/.current-rollback /opt/luminous/current
ln -sfn "$current" /opt/luminous/previous
systemctl restart luminous-api.service luminous-worker.service luminous-livekit-agent.service
/opt/luminous/current/scripts/deploy/smoke-test.sh
echo "Rolled back application code to $previous; user data was not changed."
