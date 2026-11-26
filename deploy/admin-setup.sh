#!/data/data/com.termux/files/usr/bin/bash
set -eu
umask 077
[[ $# == 0 && -t 0 && -t 1 && -t 2 ]] || exit 2
dir="$PREFIX/var/lib/tcg-hub/admin-session"
exec 8>>"$dir/lock"
flock -n 8 || exit 1
mv -f "$dir/pending" "$dir/started" || exit 1
exec "$PREFIX/bin/tcgctl" admin-setup
