#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
export TCG_FIXTURE="$fixture"
export TMPDIR="$fixture"
export PREFIX="$fixture/prefix"
export PATH="$PREFIX/bin:$PATH"
mkdir -p "$PREFIX/bin" "$fixture/stage/deploy" "$fixture/mobile" "$fixture/config"
if ! command -v python >/dev/null; then
  # Android's packaged interpreter is "python"; conventional Linux hosts may only have python3.
  printf '#!/usr/bin/env bash\nexec python3 "$@"\n' > "$PREFIX/bin/python"
  chmod +x "$PREFIX/bin/python"
fi
source "$root/deploy/exposure.sh"
aud=$(printf 'f%.0s' {1..64})
valid_public_settings https://cards.sample.org tcg.cloudflareaccess.com "$aud"
for bad_origin in http://example.org https://127.0.0.1 https://sub.localhost 'https://app.test/?q=1' ''; do
  if valid_public_settings "$bad_origin" tcg.cloudflareaccess.com "$aud"; then exit 3; fi
done
if valid_public_settings https://cards.sample.org 'bad.team.cloudflareaccess.com' "$aud"; then exit 3; fi
if valid_public_settings https://cards.sample.org tcg.cloudflareaccess.com 'none'; then exit 3; fi
config="$fixture/config"
touch "$config/tunnel.token"
write_access_settings http://127.0.0.1:8080 '' ''
if require_public_settings 2>/dev/null; then exit 3; fi
write_access_settings https://cards.sample.org tcg.cloudflareaccess.com "$aud"
require_public_settings
echo 'OK HTTPS, hostname, team and audience validation; token cannot activate local mode'

cp "$root/deploy/bootstrap-termux.sh" "$fixture/stage/deploy/"
cat > "$fixture/stage/deploy/tcgctl" <<'SH'
#!/usr/bin/env bash
set -eu
echo "$*" >> "$TCG_FIXTURE/calls"
case "$*" in
install\ --local)
  digest=$(sha256sum "$TCG_RELEASE_DIR/MANIFEST.sha256" | cut -c1-20)
  mkdir -p "$PREFIX/var/lib/tcg-hub"
  echo "$digest" > "$PREFIX/var/lib/tcg-hub/installed-manifest"
  echo "/opt/tcg-hub/releases/$digest" > "$TCG_FIXTURE/installed"
  for service in db api worker tunnel; do
    dir="$PREFIX/var/service/tcg-$service"
    mkdir -p "$dir"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$dir/run"
    chmod +x "$dir/run"
  done
  ;;
start-local) ;;
*) exit 2;;
esac
SH
cat > "$PREFIX/bin/proot-distro" <<'SH'
#!/usr/bin/env bash
set -eu
case "$*" in
  'login ubuntu-tcg --isolated -- /bin/true') [[ -f "$TCG_FIXTURE/guest" ]];;
  'install ubuntu:24.04 --name ubuntu-tcg') touch "$TCG_FIXTURE/guest";;
  'login ubuntu-tcg --isolated -- test -f /opt/tcg-hub/current/tcg-hub.jar') [[ -f "$TCG_FIXTURE/installed" ]];;
  'login ubuntu-tcg --isolated -- readlink -f /opt/tcg-hub/current') cat "$TCG_FIXTURE/installed";;
  'login ubuntu-tcg --isolated -- /bin/bash /opt/tcg-hub/current/deploy/ubuntu.sh check-local') true;;
  *) echo "Unexpected guest invocation: $*" >&2; exit 2;;
esac
SH
cat > "$PREFIX/bin/curl" <<'SH'
#!/usr/bin/env bash
case "${!#}" in
  'http://127.0.0.1:8080/internal/ready') echo '{"status":"UP"}';;
  'http://127.0.0.1:8080/api/v1/games')
    if [[ -e $TCG_FIXTURE/missing-game ]]; then
      echo '[{"code":"YUGIOH"},{"code":"POKEMON"},{"code":"WEISS"},{"code":"NIVEL"},{"code":"RIFTBOUND"}]'
    else
      echo '[{"code":"YUGIOH"},{"code":"POKEMON"},{"code":"WEISS"},{"code":"NIVEL"},{"code":"RIFTBOUND"},{"code":"ONEPIECE"}]'
    fi;;
  *) exit 2;;
esac
SH
printf '#!/usr/bin/env bash\necho aarch64\n' > "$PREFIX/bin/uname"
printf '#!/usr/bin/env bash\nexit 0\n' > "$PREFIX/bin/pkg"
chmod +x "$PREFIX/bin/"*
archive=tcg-hub-release.tar.gz
(cd "$fixture/stage" && sha256sum ./deploy/* > MANIFEST.sha256 && tar czf "$fixture/mobile/$archive" .)
(cd "$fixture/mobile" && sha256sum "$archive" > "$archive.sha256")
cp "$fixture/stage/deploy/bootstrap-termux.sh" "$fixture/mobile/"
digest=$(cut -d' ' -f1 "$fixture/mobile/$archive.sha256")
folder="$fixture/${digest:0:12}"
mv "$fixture/mobile" "$folder"
script="$folder/bootstrap-termux.sh"
printf '%s *%s\n' "$digest" "$archive" > "$folder/$archive.sha256"
bash "$script" --proof
printf '%s  %s\n' "$digest" "$archive" > "$folder/$archive.sha256"
bash "$script" --proof
[[ $(grep -Fxc 'install --local' "$fixture/calls") == 1 ]]
[[ $(grep -Fxc 'start-local' "$fixture/calls") == 2 ]]
rm -- "$PREFIX/var/lib/tcg-hub/installed-manifest"
bash "$script" --proof > /dev/null
[[ $(grep -Fxc 'install --local' "$fixture/calls") == 2 ]]
python - "$folder/tcg-hub-ready.json" "$digest" <<'PY'
import json, sys
from datetime import datetime
p = json.load(open(sys.argv[1]))
assert set(p) == {"release_sha256", "readiness", "game_count", "verified_at"}
assert p["release_sha256"] == sys.argv[2] and p["game_count"] == 6 and p["readiness"] == "UP"
assert datetime.fromisoformat(p["verified_at"]).utcoffset().total_seconds() == 0
PY
rm -- "$folder/tcg-hub-ready.json"
touch "$fixture/missing-game"
if bash "$script" --proof > /dev/null 2>&1 || [[ -e $folder/tcg-hub-ready.json ]]; then exit 3; fi
echo '# tampered' >> "$script"
if bash "$script" --proof > /dev/null 2>&1; then exit 3; fi
cp "$fixture/stage/deploy/bootstrap-termux.sh" "$script"
printf 'X' >> "$folder/$archive"
if bash "$script" --proof > /dev/null 2>&1; then exit 3; fi
echo 'OK local first install, same-release re-run, exact proof fields, incomplete catalog, changed helper and checksum failure'
