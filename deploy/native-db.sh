#!/data/data/com.termux/files/usr/bin/bash
# Termux's PostgreSQL server and matching tools use Android's packaged shared-memory library.
set -euo pipefail
umask 077
: "${PREFIX:?Run in Termux}"
state="$PREFIX/var/lib/tcg-hub-native"
data="$state/data"
pw="$state/auth/postgres.pw"
export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=tcg_hub PGUSER=postgres PGCONNECT_TIMEOUT=4
server_major() { "$PREFIX/bin/postgres" --version | awk '{print $NF}' | cut -d. -f1; }
check_data_version() {
  local disk_major
  disk_major=$(cat "$data/PG_VERSION")
  [[ $1 =~ ^[0-9]+$ && $disk_major == "$1" ]] || {
    echo "PostgreSQL data is version $disk_major. Restore a logical backup into a compatible cluster before changing major version." >&2
    exit 1
  }
}
verify_server() {
  local actual
  "$PREFIX/bin/pg_ctl" -D "$data" status >/dev/null || { echo 'Managed PostgreSQL process is down.' >&2; return 1; }
  actual=$("$PREFIX/bin/psql" -X -w -d postgres -Atc 'SHOW data_directory') || return 1
  [[ "$(realpath "$actual")" == "$(realpath "$data")" ]] || { echo 'Port 5432 belongs to a different cluster.' >&2; return 1; }
}
case "${1:-}" in
  init)
    [[ -s $pw && -r $("$PREFIX/bin/pg_config" --sharedir)/extension/postgis.control ]]
    if [[ -e $data ]]; then
      [[ -s $data/PG_VERSION ]] || { echo "Unexpected existing native data directory: $data" >&2; exit 1; }
      check_data_version "$(server_major)"
    else
      stage=$(mktemp -d "$state/.init.XXXXXX")
      trap 'rm -rf -- "$stage"' EXIT
      "$PREFIX/bin/initdb" -D "$stage" --username=postgres --pwfile="$pw" --auth=scram-sha-256 --encoding=UTF8 --locale=C
      mv -T "$stage" "$data"
    fi
    ;;
  run)
    major=$(server_major)
    check_data_version "$major"
    io_args=()
    if (( major >= 18 )); then io_args=(-c io_method=sync); fi
    exec "$PREFIX/bin/postgres" -D "$data" -h 127.0.0.1 -k "$state" -p 5432 \
      -c shared_buffers=96MB -c work_mem=2MB -c maintenance_work_mem=32MB \
      -c max_connections=16 -c max_parallel_workers=0 -c max_wal_senders=0 "${io_args[@]}"
    ;;
  stop)
    if "$PREFIX/bin/pg_ctl" -D "$data" status >/dev/null; then
      exec "$PREFIX/bin/pg_ctl" -D "$data" -m fast -w -t 45 stop
    fi
    ;;
  ready|dump|restore)
    PGPASSWORD=$(cat "$pw")
    export PGPASSWORD
    if [[ $1 == ready ]]; then
      for (( n=0; n<90; n++ )); do
        if "$PREFIX/bin/pg_isready" -q -d postgres; then break; fi
        sleep 2
      done
    fi
    verify_server
    case "$1" in
      dump) exec "$PREFIX/bin/pg_dump" -w --format=custom --file="${2:?Missing dump path}" ;;
      restore)
        blank=$("$PREFIX/bin/psql" -X -w -Atc "SELECT to_regclass('public.flyway_schema_history') IS NULL")
        case "$blank" in
          t) exec "$PREFIX/bin/pg_restore" -w --exit-on-error --single-transaction --dbname="$PGDATABASE" "${2:?Missing backup}";;
          f) ;; # A previous transaction committed before the media directory was restored.
          *) echo 'Unexpected response while checking the restore target.' >&2; exit 1;;
        esac
        ;;
    esac
    ;;
  *) echo 'native-db.sh init|run|stop|ready|dump FILE|restore FILE' >&2; exit 2 ;;
esac
