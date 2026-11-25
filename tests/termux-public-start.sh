#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
export fixture
config="$fixture/config"
mkdir -p "$fixture/app/deploy" "$config" "$fixture/bin"
cp "$root/deploy/exposure.sh" "$fixture/app/deploy/"
sed -e "s|^app=/opt/tcg-hub/current$|app=$fixture/app|" \
    -e "s|^config=/etc/tcg-hub$|config=$config|" "$root/deploy/ubuntu.sh" > "$fixture/runner"
source "$fixture/app/deploy/exposure.sh"
# Replace the transport, connector and clock. The real service entry points still run.
cat > "$fixture/bin/curl" <<'MOCK'
#!/usr/bin/env bash
[[ "$1" == --noproxy && "$2" == '*' ]] || exit 80
case "${!#}" in
  http://127.0.0.1:8080/internal/ready) [[ $database_ready == yes ]] && echo '{"status":"UP"}' ;;
  http://127.0.0.1:8080/api/v1/auth/admin-mode) printf '%s' "$mode_json" ;;
  http://127.0.0.1:20241/ready) printf '%s' "$edge_json" ;;
  *) exit 81 ;;
esac
MOCK
cat > "$fixture/bin/cloudflared" <<'MOCK'
#!/usr/bin/env bash
[[ "$*" == "tunnel --no-autoupdate --metrics 127.0.0.1:20241 run --token-file $fixture/config/tunnel.token" ]] || exit 82
touch "$fixture/connector-started"
MOCK
cat > "$fixture/bin/sleep" <<'MOCK'
#!/usr/bin/env bash
exit 71
MOCK
chmod +x "$fixture/bin/"*
export PATH="$fixture/bin:$PATH"
export TCG_TEST_PYTHON=${TCG_TEST_PYTHON:-$(command -v python3)}
python3() { "$TCG_TEST_PYTHON" "$@"; }
python() { "$TCG_TEST_PYTHON" "$@"; }
export -f python3 python
export database_ready=yes mode_json='{"mode" : "CLOUDFLARE"}' edge_json='{"status":200,"readyConnections":1}'
aud=$(printf '%064d' 0)
write_access_settings https://cards.example.org fixture.cloudflareaccess.com "$aud"
reject() { if "$@" >/dev/null 2>&1; then echo "Unexpected success: $*" >&2; exit 1; fi; }
reject bash "$fixture/runner" check-public
touch "$config/tunnel.token"
reject bash "$fixture/runner" check-public
echo 'test fixture' > "$config/tunnel.token"
bash "$fixture/runner" check-public
bash "$fixture/runner" check-public-origin
for mode_json in '{"mode":"LOCAL_TOTP"}' '{"mode":"DISABLED"}' 'bad reply'; do
  reject bash "$fixture/runner" check-public-origin
  reject bash "$fixture/runner" tunnel
  [[ ! -e $fixture/connector-started ]]
done
mode_json='{"mode":"CLOUDFLARE"}'
database_ready=no
reject bash "$fixture/runner" check-public-origin
reject bash "$fixture/runner" tunnel
[[ ! -e $fixture/connector-started ]]
database_ready=yes
bash "$fixture/runner" tunnel
[[ -e $fixture/connector-started ]]
write_access_settings http://127.0.0.1:8080 '' ''
reject bash "$fixture/runner" check-public
reject bash "$fixture/runner" tunnel

for fn in enable disable edge_ready wait_for_edge start_public_tunnel; do
  source <(sed -n "/^${fn}() {$/,/^}/p" "$root/deploy/tcgctl")
done
edge_ready
for edge_json in '{"status":200,"readyConnections":0}' '{"status":503,"readyConnections":1}' 'HTML'; do
  reject edge_ready
done
PREFIX=$fixture
svroot=$fixture/services
mkdir -p "$svroot/tcg-tunnel"
sv() { [[ $* == "up $svroot/tcg-tunnel" ]]; }
stop_service() { [[ $1 == tunnel ]] && echo stopped >> "$fixture/runlog"; }
# Make the timeout immediate while retaining its production rollback boundary.
wait_for_edge() { edge_ready; }
touch "$svroot/tcg-tunnel/down"
reject start_public_tunnel
[[ -f $svroot/tcg-tunnel/down && -s $fixture/runlog ]]
edge_json='{"status":200,"readyConnections":2}'
guest_script=/opt/tcg-hub/current/deploy/ubuntu.sh
route_ok=no
guest() {
  [[ $* == "tcgtunnel /bin/bash $guest_script check-public-route" ]] || return 1
  if [[ $route_ok == challenge ]]; then return 3; fi
  [[ $route_ok == yes ]]
}
reject start_public_tunnel
[[ -f $svroot/tcg-tunnel/down && $(wc -l < "$fixture/runlog") == 2 ]]
route_ok=challenge
start_public_tunnel
[[ ! -e $svroot/tcg-tunnel/down ]]
route_ok=yes
start_public_tunnel
[[ ! -e $svroot/tcg-tunnel/down ]]
edge_json='{"status":503,"readyConnections":0}'
reject start_public_tunnel
[[ ! -e $svroot/tcg-tunnel/down && $(wc -l < "$fixture/runlog") == 2 ]]
echo 'Passed public origin, boot guard, connector readiness and supervisor state checks.'
