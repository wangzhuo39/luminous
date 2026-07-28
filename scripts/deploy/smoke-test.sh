#!/usr/bin/env bash
set -euo pipefail

env_file="${LUMINOUS_ENV_FILE:-/etc/luminous/luminous.env}"
local_url="${LUMINOUS_LOCAL_URL:-http://127.0.0.1:8000}"
python_bin="${LUMINOUS_PYTHON:-/opt/luminous/current/.venv/bin/python}"

read_env() {
  "$python_bin" - "$env_file" "$1" <<'PY'
import sys
from pathlib import Path

path, wanted = Path(sys.argv[1]), sys.argv[2]
for line in path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        if key.strip() == wanted:
            print(value.strip().strip('"').strip("'"))
            break
PY
}

admin_token="$(read_env LUMINOUS_AUTH_TOKEN)"
public_url="$(read_env LUMINOUS_PUBLIC_URL)"
origin="$(read_env LUMINOUS_CORS_ORIGINS)"
access_code="$(read_env LUMINOUS_TESTER_ACCESS_CODE)"

for _ in $(seq 1 30); do
  if curl --fail --silent "$local_url/api/health" >/dev/null; then
    break
  fi
  sleep 2
done

deep_payload="$(curl --fail --silent --show-error -H "Authorization: Bearer $admin_token" "$local_url/api/health/deep")"
"$python_bin" -c 'import json,sys; p=json.load(sys.stdin); assert p["ok"], p' <<<"$deep_payload"

if [[ -n "$public_url" && -n "$origin" && -n "$access_code" ]]; then
  cookie_jar="$(mktemp)"
  trap 'rm -f "$cookie_jar"' EXIT
  login_body="$("$python_bin" -c 'import json,sys; print(json.dumps({"access_code":sys.argv[1]}))' "$access_code")"
  curl --fail --silent --show-error \
    -H "Origin: $origin" -H "Content-Type: application/json" \
    -c "$cookie_jar" -d "$login_body" "$public_url/api/auth/login" >/dev/null
  curl --fail --silent --show-error -H "Origin: $origin" -b "$cookie_jar" "$public_url/api/state" >/dev/null
fi

echo "Luminous API, worker heartbeat, database, model configuration, and browser session are ready."
