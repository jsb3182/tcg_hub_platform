#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
umask 077
: "${PREFIX:?Run this script in Termux on the A90}"
[[ $# == 0 || ( $# == 1 && $1 == --proof ) ]] || { echo 'Usage: bash bootstrap-termux.sh [--proof]' >&2; exit 2; }
[[ $(uname -m) == aarch64 ]] || { echo 'Requires arm64 Termux.' >&2; exit 1; }
source_dir=$(cd "$(dirname "$0")" && pwd)
archive=tcg-hub-release.tar.gz
work=$(mktemp -d "${TMPDIR:-$PREFIX/tmp}/tcg-bootstrap.XXXXXX")
trap 'rm -rf -- "$work"' EXIT

# Android shared storage is a transfer area. Verify and extract a private copy.
read -r expected filename < "$source_dir/$archive.sha256"
filename=${filename#\*}
[[ $expected =~ ^[[:xdigit:]]{64}$ && $filename == "$archive" ]] || { echo 'Invalid release checksum file.' >&2; exit 2; }
cp "$source_dir/$archive" "$work/$archive"
digest=$(sha256sum "$work/$archive" | cut -d' ' -f1)
[[ $digest == "${expected,,}" ]] || { echo 'Release checksum mismatch.' >&2; exit 2; }
folder=${source_dir##*/}
if [[ $folder =~ ^[[:xdigit:]]{12}$ && ${folder,,} != "${digest:0:12}" ]]; then
  echo 'Release digest differs from the transfer folder.' >&2; exit 2
fi
mkdir "$work/release"
tar --no-same-owner -xzf "$work/$archive" -C "$work/release"
(cd "$work/release" && sha256sum --quiet --check MANIFEST.sha256)
local_script=$(sha256sum "$source_dir/${0##*/}" | cut -d' ' -f1)
packaged_script=$(sha256sum "$work/release/deploy/bootstrap-termux.sh" | cut -d' ' -f1)
[[ $local_script == "$packaged_script" ]] || { echo 'Bootstrap differs from the verified release.' >&2; exit 2; }

pkg update -y
pkg install -y proot-distro termux-services util-linux curl coreutils tar python
if ! proot-distro login ubuntu-tcg --isolated -- /bin/true >/dev/null 2>&1; then
  proot-distro install ubuntu:24.04 --name ubuntu-tcg
fi
guest() { proot-distro login ubuntu-tcg --isolated -- "$@"; }
app=/opt/tcg-hub/current
manifest_id=$(sha256sum "$work/release/MANIFEST.sha256" | cut -c1-20)
installed=false
if guest test -f "$app/tcg-hub.jar"; then
  current=$(guest readlink -f "$app")
  [[ $current == "/opt/tcg-hub/releases/$manifest_id" ]] || { echo 'Another release is installed. Use the documented update procedure.' >&2; exit 1; }
  guest /bin/bash "$app/deploy/ubuntu.sh" check-local || { echo 'Bootstrap requires a loopback-only installation.' >&2; exit 1; }
  complete="$PREFIX/var/lib/tcg-hub/installed-manifest"
  if [[ -f $complete && $(cat "$complete") == "$manifest_id" ]]; then installed=true; fi
  for service in db api worker tunnel; do
    [[ -x $PREFIX/var/service/tcg-$service/run ]] || installed=false
  done
fi
install -m 0700 "$work/release/deploy/tcgctl" "$PREFIX/bin/tcgctl"
if [[ $installed == false ]]; then
  TCG_RELEASE_DIR="$work/release" tcgctl install --local
fi
tcgctl start-local
base=http://127.0.0.1:8080
curl -fsS --max-time 10 "$base/internal/ready" > "$work/ready.json"
curl -fsS --max-time 10 "$base/api/v1/games" > "$work/games.json"
python - "$work" "$digest" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path

work = Path(sys.argv[1])
ready = json.loads((work / "ready.json").read_text())["status"]
games = {game["code"] for game in json.loads((work / "games.json").read_text())}
if ready != "UP" or not {"YUGIOH", "POKEMON", "WEISS", "NIVEL", "RIFTBOUND"} <= games:
    raise SystemExit("Local readiness or game catalog check failed")
proof = {"release_sha256": sys.argv[2], "readiness": ready, "game_count": len(games),
         "verified_at": datetime.now(timezone.utc).isoformat()}
(work / "proof.json").write_text(json.dumps(proof) + "\n", encoding="utf-8")
PY
if [[ ${1:-} == --proof ]]; then
  proof_tmp=$(mktemp "$source_dir/.ready.XXXXXX")
  if ! cp "$work/proof.json" "$proof_tmp" || ! mv -f "$proof_tmp" "$source_dir/tcg-hub-ready.json"; then
    rm -f -- "$proof_tmp"; exit 1
  fi
fi
cat "$work/proof.json"
echo "Open $base/ on this phone."
