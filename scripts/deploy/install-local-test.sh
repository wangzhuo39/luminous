#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$(cd -- "$script_dir/../.." && pwd)"
release_ref="HEAD"
skip_tests=false

while (($#)); do
  case "$1" in
    --source) source_dir="$(cd -- "$2" && pwd)"; shift 2 ;;
    --ref) release_ref="$2"; shift 2 ;;
    --skip-tests) skip_tests=true; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root (for example: sudo $0)." >&2
  exit 1
fi

for command in git python3 tar systemctl; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done

release_sha="$(git -C "$source_dir" rev-parse --verify "$release_ref^{commit}")"
release_dir="/opt/luminous/releases/$release_sha"
current_link="/opt/luminous/current"
previous_link="/opt/luminous/previous"

if ! id luminous >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/luminous --shell /usr/sbin/nologin luminous
fi
install -d -o root -g root -m 0755 /opt/luminous/releases /etc/luminous
install -d -o luminous -g luminous -m 0700 /var/lib/luminous/runtime /var/lib/luminous/backups

if [[ ! -f /etc/luminous/luminous.env ]]; then
  install -o root -g luminous -m 0640 "$source_dir/.env.example" /etc/luminous/luminous.env
  echo "Created /etc/luminous/luminous.env. Replace every placeholder, then run this installer again." >&2
  exit 2
fi

if [[ ! -d "$release_dir" ]]; then
  install -d -o root -g root -m 0755 "$release_dir"
  git -C "$source_dir" archive "$release_sha" | tar -x -C "$release_dir"
  python3 -m venv "$release_dir/.venv"
  "$release_dir/.venv/bin/pip" install --disable-pip-version-check "$release_dir[dev]"
  if [[ -f "$release_dir/package-lock.json" ]]; then
    command -v npm >/dev/null || { echo "npm is required to test this release" >&2; exit 1; }
    (cd "$release_dir" && npm ci)
  fi
  if [[ "$skip_tests" != true ]]; then
    "$release_dir/.venv/bin/python" -m pytest "$release_dir/tests/backend" -q
    (cd "$release_dir" && npm run test:frontend)
  fi
fi

chown -R root:root "$release_dir"
if [[ -L "$current_link" ]]; then
  ln -sfn "$(readlink -f "$current_link")" "$previous_link"
fi
ln -sfn "$release_dir" /opt/luminous/.current-next
mv -Tf /opt/luminous/.current-next "$current_link"

install -o root -g root -m 0644 "$release_dir"/deploy/systemd/luminous-*.service /etc/systemd/system/
install -o root -g root -m 0644 "$release_dir/deploy/systemd/luminous-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable luminous-api.service luminous-worker.service luminous-livekit-agent.service luminous-backup.timer
systemctl restart luminous-api.service
systemctl restart luminous-worker.service
systemctl restart luminous-livekit-agent.service
systemctl start luminous-backup.timer

if ! "$current_link/scripts/deploy/smoke-test.sh"; then
  echo "Release smoke test failed; restoring the previous application release." >&2
  if [[ -L "$previous_link" ]]; then
    ln -sfn "$(readlink -f "$previous_link")" /opt/luminous/.current-rollback
    mv -Tf /opt/luminous/.current-rollback "$current_link"
    systemctl restart luminous-api.service luminous-worker.service luminous-livekit-agent.service
  fi
  exit 1
fi

echo "Installed Luminous release $release_sha"
