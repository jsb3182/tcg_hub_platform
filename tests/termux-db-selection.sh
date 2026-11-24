#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
# Exercise the selection function with isolated directory state and a simulated guest inventory.
source <(sed -n '/^choose_engine() {$/,/^}/p' "$root/deploy/tcgctl")
engine_file="$fixture/db-engine"
native_state="$fixture/native"
svroot="$fixture/services"
native_script="$fixture/native-db.sh"
engine=guest
guest_files=''
guest_credentials=yes
guest() {
  case "${!#}" in
    dir=*) printf '%s' "$guest_files";;
    'test -s /etc/tcg-hub/runtime.env'*) [[ $guest_credentials == yes ]];;
    *) return 70;;
  esac
}
reject() { if choose_engine >/dev/null 2>&1; then echo "Unexpectedly accepted $*" >&2; exit 1; fi; }
TERMUX_VERSION=googleplay.2026.10.09
choose_engine
[[ $engine == native ]]
engine=guest
TERMUX_VERSION=0.118.3
choose_engine
[[ $engine == guest ]]
TERMUX_VERSION=googleplay.2026.10.09
guest_files=/var/lib/postgresql/tcg-hub/PG_VERSION
choose_engine
[[ $engine == guest ]]
TCG_DB_ENGINE=native
reject 'switch with existing Ubuntu data'
guest_files=''
mkdir -p "$svroot/tcg-db"
echo 'old guest DB command' > "$svroot/tcg-db/run"
reject 'switch with old runner active'
touch "$svroot/tcg-db/down"
choose_engine
[[ $engine == native ]]
echo native > "$engine_file"
TCG_DB_ENGINE=guest
reject 'implicit switch from saved native engine'
TCG_DB_ENGINE=native
mkdir -p "$native_state/data" "$native_state/auth"
echo 18 > "$native_state/data/PG_VERSION"
reject 'existing native data with missing password'
echo fixture > "$native_state/auth/postgres.pw"
guest_credentials=no
reject 'existing native data with missing guest configuration'
guest_credentials=yes
choose_engine
echo 'OK Play/guest selection, protected existing clusters, stopped legacy service, private credential continuity'
