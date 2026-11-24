#!/usr/bin/env bash
# Exercise cluster selection and tool versions without opening a real port or database.
set -euo pipefail
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
root=$(cd "$(dirname "$0")/.." && pwd)
export PREFIX="$fixture/prefix"
state="$PREFIX/var/lib/tcg-hub-native"
mkdir -p "$PREFIX/bin" "$PREFIX/share/extension" "$state/auth"
printf 'fixture\n' > "$state/auth/postgres.pw"
touch "$PREFIX/share/extension/postgis.control"

cat > "$fixture/tool" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
state="$PREFIX/var/lib/tcg-hub-native"
case "${0##*/}" in
  postgres)
    if [[ $1 == --version ]]; then echo 'postgres (PostgreSQL) 18.3'; else
      printf '%s\n' "$@" > "$state/server-args"
    fi
    ;;
  pg_config) [[ $1 == --sharedir ]]; echo "$PREFIX/share" ;;
  initdb)
    [[ $1 == -D && $2 == "$state"/.init.* ]]
    printf '18\n' > "$2/PG_VERSION"
    [[ ! -e $state/fail-init ]]
    ;;
  pg_ctl) [[ $1 == -D && $2 == "$state/data" && $3 == status ]] ;;
  psql)
    [[ $PGHOST == 127.0.0.1 && $PGPORT == 5432 && $PGPASSWORD == fixture ]]
    case "${!#}" in
      'SHOW data_directory') cat "$state/actual-cluster" ;;
      *flyway_schema_history*) cat "$state/blank" ;;
      *) exit 3 ;;
    esac
    ;;
  pg_dump)
    [[ $PGDATABASE == tcg_hub && $* == "-w --format=custom --file=$state/snapshot.dump" ]]
    touch "$state/snapshot.dump"
    ;;
  pg_restore)
    [[ $PGDATABASE == tcg_hub && $* == "-w --exit-on-error --single-transaction --dbname=tcg_hub $state/snapshot.dump" ]]
    touch "$state/applied"
    ;;
  *) exit 3 ;;
esac
SH
for tool in postgres pg_config initdb pg_ctl psql pg_dump pg_restore; do
  install -m 700 "$fixture/tool" "$PREFIX/bin/$tool"
done
native() { bash "$root/deploy/native-db.sh" "$@"; }
should_fail() { if "$@" > /dev/null 2>&1; then echo "Unexpected success: $*" >&2; exit 1; fi; }

touch "$state/fail-init"
should_fail native init
[[ ! -e $state/data && -z $(find "$state" -maxdepth 1 -name '.init.*' -print -quit) ]]
rm "$state/fail-init"
native init
[[ $(cat "$state/data/PG_VERSION") == 18 ]]
printf '16\n' > "$state/data/PG_VERSION"
should_fail native init
should_fail native run
[[ $(cat "$state/data/PG_VERSION") == 16 && ! -e $state/server-args ]]
printf '18\n' > "$state/data/PG_VERSION"
native run
grep -Fxq 127.0.0.1 "$state/server-args"
grep -Fxq 'max_connections=16' "$state/server-args"

printf '%s\n' "$fixture" > "$state/actual-cluster"
should_fail native dump "$state/snapshot.dump"
should_fail native restore "$state/snapshot.dump"
[[ ! -e $state/snapshot.dump && ! -e $state/applied ]]
printf '%s\n' "$state/data" > "$state/actual-cluster"
native dump "$state/snapshot.dump"
printf 't\n' > "$state/blank"
native restore "$state/snapshot.dump"
[[ -f $state/snapshot.dump && -f $state/applied ]]
rm "$state/applied"
printf 'f\n' > "$state/blank"
native restore "$state/snapshot.dump"
[[ ! -e $state/applied ]]
echo 'OK native PostgreSQL initialization, major-version guard, cluster identity and matching dump/restore tools'
