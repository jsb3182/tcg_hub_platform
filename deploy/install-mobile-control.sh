#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${PREFIX:?Run in Termux}"
src=$(cd "$(dirname "$0")" && pwd)
base="$PREFIX/libexec/tcg-hub"
svroot="$PREFIX/var/service"
service="$svroot/tcg-mobile"
mkdir -p "$svroot"
install -d -m 0700 "$base" "$HOME/tcg-control"
temp=$(mktemp "$base/.mobile-control.XXXXXX")
install -m 0600 "$src/mobile-control.py" "$temp"
mv -f "$temp" "$base/mobile-control.py"
if [[ ! -d $service ]]; then
  staging=$(mktemp -d "$svroot/.tcg-mobile.XXXXXX")
  printf '#!%s/bin/sh\nexec "%s/bin/python" -I "%s/mobile-control.py"\n' "$PREFIX" "$PREFIX" "$base" > "$staging/run"
  chmod 0700 "$staging/run"
  mv -T "$staging" "$service"
else
  sv -w 15 restart "$service"
fi
