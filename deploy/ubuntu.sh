#!/usr/bin/env bash
set -euo pipefail
umask 077
pgbin=/usr/lib/postgresql/16/bin
pgdata=/var/lib/postgresql/tcg-hub
app=/opt/tcg-hub/current
config=/etc/tcg-hub
state=/var/lib/tcg-hub
cd "$app"
source "$app/deploy/exposure.sh"
cmd=${1:-}
shift || true
if [[ $cmd == db ]]; then
  if [[ ! -s $pgdata/PG_VERSION ]]; then
    "$pgbin/initdb" -D "$pgdata" --username=postgres --pwfile="$config/postgres.pw" --auth=scram-sha-256 --encoding=UTF8 --locale=C.UTF-8
  fi
  exec "$pgbin/postgres" -D "$pgdata" -h 127.0.0.1 -k "$pgdata" -p 5432 \
    -c shared_buffers=96MB -c work_mem=2MB -c maintenance_work_mem=32MB \
    -c max_connections=16 -c max_parallel_workers=0 -c max_wal_senders=0
fi
if [[ $cmd == check-public-route ]]; then
  require_public_settings
  exec python3 -I "$app/deploy/check-public.py" "$PUBLIC_ORIGIN" "$CF_TEAM_DOMAIN"
fi
if [[ $cmd == tunnel || $cmd == check-public || $cmd == check-public-origin ]]; then
  require_public_settings
  [[ -f $config/tunnel.token && -r $config/tunnel.token && -s $config/tunnel.token ]] && command -v cloudflared >/dev/null || { echo 'Public start requires an installed connector and a readable, nonempty token file.' >&2; exit 1; }
  if [[ $cmd == check-public ]]; then exit 0; fi
  if [[ $cmd == check-public-origin ]]; then
    public_origin_ready || { echo 'The running API must be ready and use Cloudflare Access before public start.' >&2; exit 1; }
    exit 0
  fi
  until public_origin_ready; do sleep 5; done
  exec cloudflared tunnel --no-autoupdate --metrics 127.0.0.1:20241 run --token-file "$config/tunnel.token"
fi
if [[ $cmd == totp ]]; then
  require_local_settings
  exec /usr/bin/env -i PATH=/usr/bin:/bin LANG=C.UTF-8 "$app/venv/bin/python" -I "$app/deploy/enroll-totp.py" "$@"
fi
if [[ $cmd == admin-setup ]]; then
  require_local_settings
  exec /usr/bin/env -i PATH=/usr/bin:/bin LANG=C.UTF-8 "$app/venv/bin/python" -I "$app/deploy/enroll-totp.py" --setup
fi
source "$config/runtime.env"
source "$config/access.env"
if [[ $cmd == worker || $cmd == media ]]; then
  export CATALOG_CACHE_ROOT=/var/lib/tcg-hub/catalog-cache
  if [[ -r $config/feeds.env ]]; then source "$config/feeds.env"; fi
  if [[ -r $config/x.token ]]; then
    X_BEARER_TOKEN=$(cat "$config/x.token")
    export X_BEARER_TOKEN
  fi
fi
admin_db() {
  PGUSER=postgres PGPASSWORD="$(cat "$config/postgres.pw")" "$@"
}
case "$cmd" in
  native-auth)
    # The bind target is a private Termux directory, never Android shared storage.
    dest=/mnt/tcg-auth/postgres.pw
    if [[ -e $dest ]]; then
      cmp -s "$config/postgres.pw" "$dest" || { echo 'Native and guest database credentials differ.' >&2; exit 1; }
    else
      tmp=$(mktemp /mnt/tcg-auth/.pw.XXXXXX)
      trap 'rm -f -- "$tmp"' EXIT
      cat "$config/postgres.pw" > "$tmp"
      mv -T "$tmp" "$dest"
    fi
    ;;
  configure-public)
    [[ $# == 3 ]] && valid_public_settings "$1" "$2" "$3" || { echo 'Expected HTTPS_ORIGIN TEAM.cloudflareaccess.com APP_AUD.' >&2; exit 2; }
    export DEBIAN_FRONTEND=noninteractive
    install_tunnel_package
    write_access_settings "$1" "$2" "$3"
    ;;
  check-local)
    require_local_settings
    ;;
  prepare-db)
    for (( n=0; n<90; n++ )); do
      if admin_db pg_isready -q -d postgres; then break; fi
      sleep 2
    done
    admin_db psql -X --set=ON_ERROR_STOP=1 -d postgres <<'SQL'
\getenv app_password DB_PASSWORD
SELECT format('CREATE ROLE tcg_app LOGIN PASSWORD %L', :'app_password')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='tcg_app') \gexec
SELECT 'CREATE DATABASE tcg_hub'
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='tcg_hub') \gexec
SQL
    admin_db psql -X --set=ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE tcg_hub TO tcg_app;
GRANT USAGE, CREATE ON SCHEMA public TO tcg_app;
DO $$
BEGIN
 IF to_regclass('public.flyway_schema_history') IS NULL AND EXISTS (
   SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND NOT EXISTS (
     SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass
       AND d.objid=c.oid AND d.deptype='e'
   ) AND c.relkind IN ('r','p','v','m','S','f')
 ) THEN RAISE EXCEPTION 'This database already has unrelated objects; supply a dedicated tcg_hub database.';
 END IF;
END $$;
SQL
    psql -X --set=ON_ERROR_STOP=1 -c 'SELECT PostGIS_Version()'
    ;;
  api)
    until pg_isready -q; do sleep 3; done
    exec java -Xms256m -Xmx1024m -XX:ActiveProcessorCount=2 -jar tcg-hub.jar --spring.config.import=optional:configtree:/etc/tcg-hub/web-config/
    ;;
  worker)
    until curl -fsS --max-time 4 http://127.0.0.1:8080/internal/ready >/dev/null 2>&1; do sleep 5; done
    cd crawler-middleware
    exec "$app/venv/bin/python" -m tcg_worker run
    ;;
  account)
    [[ $# == 2 && ( $2 == ROLE_ADMIN || $2 == ROLE_USER ) ]] || { echo 'account EMAIL ROLE_ADMIN|ROLE_USER' >&2; exit 2; }
    exec java -Xms128m -Xmx384m -XX:ActiveProcessorCount=2 -jar tcg-hub.jar "--provision-account=$1" "--account-role=$2"
    ;;
  password)
    [[ $# == 1 ]] || exit 2
    exec java -Xms128m -Xmx384m -XX:ActiveProcessorCount=2 -jar tcg-hub.jar "--change-password=$1"
    ;;
  media)
    cd crawler-middleware
    exec "$app/venv/bin/python" -m tcg_worker "$@"
    ;;
  backup)
    psql -X --set=ON_ERROR_STOP=1 -qAtc 'SELECT 1 FROM public.flyway_schema_history LIMIT 1' >/dev/null
    parent=/mnt/tcg-backups
    native=false
    if [[ ${1:-} == --native ]]; then native=true; shift; fi
    name="$(date -u +%Y%m%dT%H%M%SZ)-$$"
    if [[ $# != 0 ]]; then
      [[ $# == 2 && $1 == --name && $2 =~ ^[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]] || exit 2
      name=$2
    fi
    target="$parent/$name"
    [[ ! -e $target ]] || { echo 'This backup directory already exists.' >&2; exit 1; }
    tmp=$(mktemp -d "$parent/.incomplete.XXXXXX")
    trap 'rm -rf -- "$tmp"' EXIT
    if [[ $native == true ]]; then
      cp /mnt/tcg-native/db.dump "$tmp/db.dump"
    else
      admin_db pg_dump --format=custom --file="$tmp/db.dump"
    fi
    tar -C "$state" -czf "$tmp/files.tar.gz" media spool
    (cd "$tmp" && sha256sum db.dump files.tar.gz > SHA256SUMS)
    mv -T "$tmp" "$target"
    echo "Created ${target##*/}"
    ;;
  restore|restore-stage|restore-finish)
    [[ ${1:-} =~ ^[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]] || { echo 'restore expects a backup directory name' >&2; exit 2; }
    cd "/mnt/tcg-backups/$1"
    sha256sum --check SHA256SUMS
    staging="$state/restore-in-progress"
    blank=$(admin_db psql -XAtc "SELECT to_regclass('public.flyway_schema_history') IS NULL")
    if [[ -d $staging ]]; then
      [[ $(cat "$staging/backup-name") == "$1" ]] || { echo 'Finish the active backup restore first.' >&2; exit 1; }
    else
      [[ $cmd != restore-finish ]] || { echo 'Missing staged restore.' >&2; exit 1; }
      [[ $blank == t && -z $(find "$state/media" "$state/spool" -mindepth 1 -print -quit) ]] || {
        echo 'Restore requires a fresh database and empty media and spool directories.' >&2; exit 1;
      }
      temp=$(mktemp -d "$state/.extract.XXXXXX")
      trap 'rm -rf -- "$temp"' EXIT
      tar -C "$temp" --no-same-owner -xzf files.tar.gz
      chown -R tcgapp:tcgapp "$temp/media" "$temp/spool"
      echo "$1" > "$temp/backup-name"
      mv -T "$temp" "$staging"
    fi
    if [[ $cmd == restore-stage ]]; then exit 0; fi
    if [[ $cmd == restore && $blank == t ]]; then
      admin_db pg_restore --exit-on-error --single-transaction --dbname="$PGDATABASE" db.dump
    fi
    [[ $(admin_db psql -XAtc "SELECT to_regclass('public.flyway_schema_history') IS NOT NULL") == t ]] || {
      echo 'Database restore has not completed.' >&2; exit 1;
    }
    for directory in media spool; do
      if [[ -d $staging/$directory ]]; then mv -T "$staging/$directory" "$state/$directory"; fi
    done
    mv -T "$staging" "$state/.restored-$1"
    rm -f "$state/.restored-$1/backup-name"
    rmdir "$state/.restored-$1"
    ;;
  *) echo "Unknown operation: $cmd" >&2; exit 2;;
esac
