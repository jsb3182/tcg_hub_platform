#!/usr/bin/env bash
# Run inside the Ubuntu guest, from the extracted release.
set -euo pipefail
umask 077
release=$(cd "$(dirname "$0")/.." && pwd)
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $(dpkg --print-architecture) == arm64 ]] || {
  echo 'Requires Ubuntu 24.04 arm64.' >&2; exit 1;
}
cd "$release"
sha256sum --quiet --check MANIFEST.sha256
config=/etc/tcg-hub
base=/opt/tcg-hub
if [[ ! -s $config/runtime.env ]]; then
  [[ ${1:-} =~ ^https://[A-Za-z0-9.-]+$ && ${2:-} =~ ^[A-Za-z0-9-]+\.cloudflareaccess\.com$ && ${3:-} =~ ^[[:xdigit:]]{64}$ ]] || {
    echo 'Usage (first install): bash deploy/install-ubuntu.sh https://PUBLIC_HOST TEAM.cloudflareaccess.com APP_AUD' >&2
    exit 2
  }
fi
export DEBIAN_FRONTEND=noninteractive
install -d -m 0755 /etc/postgresql-common/createcluster.d /usr/share/keyrings
printf '%s\n' 'create_main_cluster = false' > /etc/postgresql-common/createcluster.d/99-tcg.conf
# Minimal Ubuntu images generally ship a policy-rc.d already.
if [[ ! -e /usr/sbin/policy-rc.d ]]; then
  printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
  chmod 0755 /usr/sbin/policy-rc.d
  trap 'rm -f /usr/sbin/policy-rc.d' EXIT
fi
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl
curl --fail --silent --show-error --location https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
chmod 0644 /usr/share/keyrings/cloudflare-main.gpg
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared noble main' > /etc/apt/sources.list.d/tcg-cloudflared.list
chmod 0644 /etc/apt/sources.list.d/tcg-cloudflared.list
apt-get update
apt-get install -y --no-install-recommends openjdk-17-jre-headless postgresql-16 postgresql-16-postgis-3 python3-venv libpq5 openssl cloudflared
apt-get clean
id tcgapp >/dev/null 2>&1 || useradd --system --create-home --user-group tcgapp
id tcgtunnel >/dev/null 2>&1 || useradd --system --create-home --user-group tcgtunnel
install -d -m 0755 "$config" "$base" "$base/releases"
install -d -m 0700 -o tcgapp -g tcgapp /var/lib/tcg-hub /var/lib/tcg-hub/{media,spool,catalog-cache}
install -d -m 0700 -o postgres -g postgres /var/lib/postgresql/tcg-hub
if [[ ! -s $config/postgres.pw ]]; then
  [[ ! -e /var/lib/postgresql/tcg-hub/PG_VERSION ]] || { echo 'Existing cluster needs its original postgres.pw.' >&2; exit 1; }
  openssl rand -hex 32 > "$config/postgres.pw"
fi
chown postgres:postgres "$config/postgres.pw"
chmod 0600 "$config/postgres.pw"
if [[ ! -s $config/runtime.env ]]; then
  temp_env=$(mktemp "$config/runtime.XXXXXX")
  {
    printf 'export PUBLIC_ORIGIN=%q\nexport CF_TEAM_DOMAIN=%q\nexport CF_AUDIENCE=%q\n' "$1" "$2" "$3"
    echo "export JWT_SECRET=$(openssl rand -base64 48)"
    echo "export DB_PASSWORD=$(openssl rand -hex 32)"
    cat <<'ENV'
export DB_USER=tcg_app
export DB_URL=jdbc:postgresql://127.0.0.1:5432/tcg_hub
export PGUSER="$DB_USER" PGPASSWORD="$DB_PASSWORD"
export PGDATABASE=tcg_hub PGHOST=127.0.0.1 PGPORT=5432
export MEDIA_ROOT=/var/lib/tcg-hub/media SPOOL_ROOT=/var/lib/tcg-hub/spool
export WORKER_POLL_SECONDS=15
export SERVER_ADDRESS=127.0.0.1 SERVER_PORT=8080
export SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=4
export SPRING_DATASOURCE_HIKARI_MINIMUM_IDLE=1
export SPRING_FLYWAY_BASELINE_ON_MIGRATE=true SPRING_FLYWAY_BASELINE_VERSION=0
export SERVER_TOMCAT_THREADS_MAX=16 SERVER_TOMCAT_THREADS_MIN_SPARE=2
ENV
  } > "$temp_env"
  chown tcgapp:tcgapp "$temp_env"
  mv "$temp_env" "$config/runtime.env"
fi
# Name by manifest digest so that a failed upgrade leaves the previous files usable.
digest=$(sha256sum MANIFEST.sha256 | cut -c 1-20)
dest="$base/releases/$digest"
if [[ ! -f $dest/.installed ]]; then
  install -d -m 0755 "$dest"
  cp -R tcg-hub.jar crawler-middleware deploy docs MANIFEST.sha256 "$dest/"
  (cd "$dest" && sha256sum --quiet --check MANIFEST.sha256)
  python3 -m venv "$dest/venv"
  "$dest/venv/bin/pip" install --no-cache-dir --only-binary=:all: -r "$dest/crawler-middleware/requirements.txt"
  chmod -R a+rX "$dest"
  touch "$dest/.installed"
fi
ln -sfn "$dest" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
echo "Installed $dest"
