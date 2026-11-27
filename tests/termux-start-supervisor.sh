#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
export HOME="$fixture/home" PREFIX="$fixture/prefix"
export PATH="$fixture/bin:$PATH"
svroot="$PREFIX/var/service"
mkdir -p "$fixture/bin" "$HOME/.termux/boot" "$svroot"/tcg-{db,api,worker,tunnel}
touch "$svroot"/tcg-{api,worker,tunnel}/down
cat > "$fixture/bin/sv" <<'MOCK'
#!/usr/bin/env bash
set -eu
if [[ $1 == status ]]; then
  shift
  for service in "$@"; do [[ -e $service/supervised ]] || exit 31; done
elif [[ $1 == up ]]; then
  [[ -e $2/supervised && ! -e $2/down ]]
  touch "$2/running"
else
  [[ $1 == -w && $3 == stop && -e $4/supervised && -f $4/down ]]
  rm -f "$4/running"
  printf '%s\n' "${4##*/}" >> "$HOME/confirmed-stops"
fi
MOCK
cat > "$HOME/.termux/boot/30-tcg-services" <<'MOCK'
#!/usr/bin/env bash
set -eu
[[ ! -e /proc/self/fd/9 ]]
for name in api worker tunnel; do [[ -f "$PREFIX/var/service/tcg-$name/down" ]]; done
echo start >> "$HOME/boot-events"
touch "$PREFIX/var/service"/tcg-{db,api,worker,tunnel}/supervised
MOCK
for name in proot-distro curl flock; do
  printf '#!/usr/bin/env bash\nexit 0\n' > "$fixture/bin/$name"
done
chmod +x "$HOME/.termux/boot/30-tcg-services" "$fixture/bin/"*
bash "$root/deploy/tcgctl" start-local
[[ -f $svroot/tcg-tunnel/down && ! -e $svroot/tcg-api/down && ! -e $svroot/tcg-worker/down ]]
bash "$root/deploy/tcgctl" start-local
[[ $(wc -l < "$HOME/boot-events") == 1 ]]
# A90 can lose a single runsv while PostgreSQL and the application processes remain up.
rm "$svroot/tcg-worker/supervised"
[[ -f $svroot/tcg-db/supervised && -f $svroot/tcg-db/running && -f $svroot/tcg-worker/running ]]
for attempt in 1 2; do
  : > "$HOME/confirmed-stops"
  bash "$root/deploy/tcgctl" maintenance
  [[ $(wc -l < "$HOME/boot-events") == 2 ]]
  [[ -f $svroot/tcg-db/running && ! -e $svroot/tcg-db/down ]]
  for name in tunnel worker api; do
    [[ -f $svroot/tcg-$name/down && ! -e $svroot/tcg-$name/running ]]
    grep -Fxq "tcg-$name" "$HOME/confirmed-stops"
  done
done
bash "$root/deploy/tcgctl" stop
for name in db api worker tunnel; do [[ -f "$svroot/tcg-$name/down" && ! -e "$svroot/tcg-$name/running" ]]; done
[[ $(wc -l < "$HOME/boot-events") == 2 ]]
echo 'Passed private start, lost worker supervision, repeat maintenance and confirmed stop.'
