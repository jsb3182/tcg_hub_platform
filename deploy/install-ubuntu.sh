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
source "$release/deploy/exposure.sh"
local_origin=http://127.0.0.1:8080
if [[ -s $config/runtime.env ]]; then
  # Pre-access.env releases kept the three settings in the private runtime file.
  source "$config/runtime.env"
  if [[ -r $config/access.env ]]; then source "$config/access.env"; fi
  if [[ $# == 1 && $1 == --local ]]; then
    [[ ${PUBLIC_ORIGIN:-} == "$local_origin" && -z ${CF_TEAM_DOMAIN:-} && -z ${CF_AUDIENCE:-} ]] || {
      echo 'This installation already has public settings.' >&2; exit 2;
    }
  elif [[ $# != 0 ]] && ! { [[ $# == 3 ]] && [[ $1 == "${PUBLIC_ORIGIN:-}" && $2 == "${CF_TEAM_DOMAIN:-}" && $3 == "${CF_AUDIENCE:-}" ]]; }; then
    echo 'Use tcgctl configure-public to change Access settings on an existing installation.' >&2; exit 2
  fi
elif [[ $# == 1 && $1 == --local ]]; then
  PUBLIC_ORIGIN=$local_origin CF_TEAM_DOMAIN='' CF_AUDIENCE=''
elif [[ $# == 3 ]] && valid_public_settings "$1" "$2" "$3"; then
  PUBLIC_ORIGIN=$1 CF_TEAM_DOMAIN=$2 CF_AUDIENCE=$3
else
  echo 'First install requires --local or HTTPS_ORIGIN TEAM.cloudflareaccess.com APP_AUD.' >&2; exit 2
fi
if [[ ${PUBLIC_ORIGIN:-} != "$local_origin" || -n ${CF_TEAM_DOMAIN:-} || -n ${CF_AUDIENCE:-} ]]; then
  valid_public_settings "${PUBLIC_ORIGIN:-}" "${CF_TEAM_DOMAIN:-}" "${CF_AUDIENCE:-}" || { echo 'Invalid existing Access settings.' >&2; exit 2; }
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
apt-get install -y --no-install-recommends ca-certificates curl openjdk-17-jre-headless postgresql-16 postgresql-16-postgis-3 python3-venv libpq5 openssl
if [[ $PUBLIC_ORIGIN != "$local_origin" ]]; then install_tunnel_package; fi
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
write_access_settings "$PUBLIC_ORIGIN" "${CF_TEAM_DOMAIN:-}" "${CF_AUDIENCE:-}"
if [[ ! -s $config/runtime.env ]]; then
  temp_env=$(mktemp "$config/runtime.XXXXXX")
  {
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
