#!/bin/sh
# Run on a Linux kernel with util-linux flock. ash also supports the file identity test.
set -eu
root=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
export HOME="$tmp/home" PREFIX="$tmp/prefix"
mkdir -p "$HOME" "$PREFIX/var/service/tcg-tunnel" "$PREFIX/bin"
touch "$PREFIX/var/service/tcg-tunnel/down"
printf '#!/bin/sh\necho run:\n' > "$PREFIX/bin/sv"
chmod +x "$PREFIX/bin/sv"
export PATH="$PREFIX/bin:$PATH"
if command -v bash >/dev/null; then
  manage() { bash "$root/deploy/tcgctl" status; }
else
  # Minimal WSL distributions sometimes have ash only. Exercise the exact two
  # production lock statements, with a real child process and separate open.
  sed -n '/^if \[\[ ! \/proc\/self\/fd\/9 /,+1p' "$root/deploy/tcgctl" > "$tmp/lock"
  [ "$(wc -l < "$tmp/lock")" -eq 2 ]
  manage() { /bin/sh -e "$tmp/lock"; }
fi
exec 9>"$HOME/.tcg-control.lock"
flock -n 9
manage >/dev/null
if (exec 9>&-; manage >/dev/null 2>&1); then echo 'Separate process bypassed lock' >&2; exit 1; fi
exec 9>&-
manage >/dev/null
echo 'OK real Linux flock: inherited descriptor reenters, independent command waits for release.'
