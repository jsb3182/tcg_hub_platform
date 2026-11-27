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
if [[ $1 == status ]]; then [[ -f $HOME/supervisor ]]; exit; fi
[[ -f $HOME/supervisor ]] || exit 31
if [[ $1 == up ]]; then [[ ! -e $2/down ]]; exit; fi
[[ $3 == stop && -f $4/down ]]
MOCK
cat > "$HOME/.termux/boot/30-tcg-services" <<'MOCK'
#!/usr/bin/env bash
set -eu
[[ ! -e /proc/self/fd/9 ]]
for name in api worker tunnel; do [[ -f "$PREFIX/var/service/tcg-$name/down" ]]; done
echo start >> "$HOME/boot-events"
touch "$HOME/supervisor"
MOCK
for name in proot-distro curl flock; do
  printf '#!/usr/bin/env bash\nexit 0\n' > "$fixture/bin/$name"
done
chmod +x "$HOME/.termux/boot/30-tcg-services" "$fixture/bin/"*
bash "$root/deploy/tcgctl" start-local
[[ -f $svroot/tcg-tunnel/down && ! -e $svroot/tcg-api/down && ! -e $svroot/tcg-worker/down ]]
bash "$root/deploy/tcgctl" start-local
[[ $(wc -l < "$HOME/boot-events") == 1 ]]
bash "$root/deploy/tcgctl" stop
for name in db api worker tunnel; do [[ -f "$svroot/tcg-$name/down" ]]; done
[[ $(wc -l < "$HOME/boot-events") == 1 ]]
echo 'Passed explicit supervisor recovery, private start and persistent stop.'
