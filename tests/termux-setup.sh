#!/usr/bin/env bash
# Offline end-to-end setup entry using two immutable release fixtures and isolated services.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
export F=$fixture HOME="$fixture/home" PREFIX="$fixture/prefix" TMPDIR="$fixture/tmp"
export PATH="$PREFIX/bin:$PATH"
mkdir -p "$HOME" "$PREFIX/bin" "$TMPDIR" "$F/config" "$F/app" "$F/stage/deploy"
tag1=a90-2026.11.25.3 tag2=a90-2026.11.25.4 tag3=a90-2026.11.25.10
helper="$root/deploy/setup-termux.sh"
cp "$helper" "$root/deploy/bootstrap-termux.sh" "$F/stage/deploy"
cat > "$PREFIX/bin/proot-distro" <<'SH'
#!/usr/bin/env bash
set -eu
case "$*" in
  'login ubuntu-tcg --isolated -- /bin/true') [[ -e $F/ubuntu ]];;
  'install ubuntu:24.04 --name ubuntu-tcg') touch "$F/ubuntu";;
  'login ubuntu-tcg --isolated -- /bin/bash -se -- /etc/tcg-hub /opt/tcg-hub/current /var/lib/tcg-hub/restore-in-progress')
    bash -se -- "$F/config" "$F/app/current" "$F/restore";;
  *) exit 2;;
esac
SH
# Use an ordinary directory to model the guest symlink on Windows checkouts.
cat > "$PREFIX/bin/readlink" <<'SH'
#!/usr/bin/env bash
if [[ $* == "-f $F/app/current" ]]; then printf '%s/releases/%s\n' "$F/app" "$(cat "$F/current-id")"; else exec /usr/bin/readlink "$@"; fi
SH
cat > "$PREFIX/bin/curl" <<'SH'
#!/usr/bin/env bash
set -eu
url=${!#}
origin=https://github.com/jsb3182/tcg_hub_platform/releases
case "$url" in
  "$origin/latest") echo "$origin/tag/$(cat "$F/latest")";;
  "$origin/download/"*)
    target=${url#"$origin/download/"}
    while [[ $1 != --output ]]; do shift; done
    cp "$F/assets/$target" "$2"; echo "$target" >> "$F/downloads";;
  http://127.0.0.1:8080/internal/ready) [[ -f $F/running ]] && echo '{"status":"UP"}';;
  http://127.0.0.1:8080/api/v1/games)
    if [[ -f $F/missing-game ]]; then echo '[]'; else
      echo '[{"code":"YUGIOH"},{"code":"POKEMON"},{"code":"WEISS"},{"code":"NIVEL"},{"code":"RIFTBOUND"}]'; fi;;
  *) exit 2;;
esac
SH
cat > "$PREFIX/bin/sv" <<'SH'
#!/usr/bin/env bash
if [[ $1 == status ]]; then
  if [[ -f $F/running ]]; then echo 'run: fixture'; else echo 'down: fixture'; fi
elif [[ $* != "-w 30 up $PREFIX/var/service/tcg-mobile" ]]; then exit 2; fi
SH
cat > "$PREFIX/bin/flock" <<'SH'
#!/usr/bin/env bash
[[ $* == '-n 9' && ! -e $F/busy ]]
SH
printf '#!/usr/bin/env bash\necho aarch64\n' > "$PREFIX/bin/uname"
chmod +x "$PREFIX/bin/"*
cat > "$F/stage/deploy/tcgctl" <<'SH'
#!/usr/bin/env bash
set -eu
echo "$*" >> "$F/ops"
services="$PREFIX/var/service"
case "$1" in
 service-controls)
   [[ $0 == "$TCG_RELEASE_DIR/deploy/tcgctl" ]]
   sha256sum "$TCG_RELEASE_DIR/tcg-hub.jar" | cut -d' ' -f1 > "$F/controls";;
 maintenance)
   [[ -f $F/controls && $(cat "$F/controls") == "$(sha256sum "$TCG_RELEASE_DIR/tcg-hub.jar" | cut -d' ' -f1)" ]]
   rm "$F/controls"
   rm -f "$F/running"
   for member in tunnel api worker; do touch "$services/tcg-$member/down"; done;;
 backup-for-update)
   folder="$HOME/tcg-backups/$2"; mkdir -p "$folder"
   (cd "$folder"; cp "$F/userdata" db.dump; echo media > files.tar.gz; sha256sum db.dump files.tar.gz > SHA256SUMS)
   if [[ -e $F/fail-after-backup ]]; then rm -f "$F/fail-after-backup"; exit 1; fi;;
 install)
   [[ $2 == --local ]]
   mkdir -p "$F/app/current" "$HOME/.termux/boot"
   printf '%s\n' 'export PUBLIC_ORIGIN=http://127.0.0.1:8080' > "$F/config/access.env"
   cp "$TCG_RELEASE_DIR/MANIFEST.sha256" "$F/app/current/"
   cp "$TCG_RELEASE_DIR/tcg-hub.jar" "$F/app/current/"
   touch "$F/app/current/.installed"
   sha256sum "$TCG_RELEASE_DIR/MANIFEST.sha256" | cut -c1-20 > "$F/current-id"
   if [[ -e $F/fail-install ]]; then rm -f "$F/fail-install"; exit 1; fi
   for member in tunnel api worker db mobile; do
     mkdir -p "$services/tcg-$member"; touch "$services/tcg-$member/down"
     printf '#!/usr/bin/env bash\n:\n' > "$services/tcg-$member/run"
     chmod +x "$services/tcg-$member/run"
   done
   cp "$F/current-id" "$PREFIX/var/lib/tcg-hub/installed-manifest"
   echo : > "$HOME/.termux/boot/30-tcg-services";;
 start-local)
   rm -f "$services/tcg-api/down" "$services/tcg-worker/down" "$services/tcg-db/down"
   touch "$F/running";;
 *) exit 2;;
esac
SH
bundle() {
  local tag=$1 out="$F/assets/$1" archive=tcg-hub-release.tar.gz
  mkdir -p "$out"
  echo "$tag" > "$F/stage/tcg-hub.jar"
  (cd "$F/stage"; sha256sum ./tcg-hub.jar ./deploy/* > MANIFEST.sha256; tar czf "$out/$archive" .)
  cp "$F/stage/deploy/bootstrap-termux.sh" "$out"
  (cd "$out"; sha256sum "$archive" > "$archive.sha256")
}
for tag in "$tag1" "$tag2" "$tag3"; do bundle "$tag"; done
count() { grep -c "^$1" "$F/ops" || true; }
reject() { if bash "$helper" "$@" > "$F/output" 2>&1; then echo 'Expected setup to refuse.' >&2; exit 1; fi; }
run() { bash "$helper" "$@" > "$F/output" || { cat "$F/output" >&2; exit 1; }; }
touch "$F/ops"; echo "$tag1" > "$F/latest"
reject --release '../wrong'
touch "$F/busy"; reject; rm "$F/busy"
[[ ! -e $F/downloads ]]
# Stranded tcgctl binary and halfway guest switch must be repairable without a backup.
touch "$PREFIX/bin/tcgctl" "$F/fail-install"; chmod +x "$PREFIX/bin/tcgctl"
reject
[[ $(count install) == 1 && $(count backup) == 0 && ! -f $PREFIX/var/lib/tcg-hub/installed-manifest ]]
echo "$tag2" > "$F/latest"
reject --release "$tag2"
run
[[ $(count install) == 2 && $(count backup) == 0 && $(count start-local) == 1 ]]
run --release "$tag1"
[[ $(count install) == 2 && $(count start-local) == 1 && $(count maintenance) == 0 ]]
# Corrupt inputs and public configuration never stop a running server.
printf 'original database\n' > "$F/userdata"
asset="$F/assets/$tag2/bootstrap-termux.sh"; mv "$asset" "$asset.good"; echo broken > "$asset"
reject --release "$tag2"; mv "$asset.good" "$asset"
arc="$F/assets/$tag2/tcg-hub-release.tar.gz"; cp "$arc" "$arc.good"; echo broken >> "$arc"
reject --release "$tag2"; mv "$arc.good" "$arc"
signed_digest=$(sha256sum "$arc" | cut -d' ' -f1)
cp "$arc" "$arc.good"; cp "$arc.sha256" "$arc.sha256.good"
cp "$F/assets/$tag3/tcg-hub-release.tar.gz" "$arc"
(cd "${arc%/*}"; sha256sum tcg-hub-release.tar.gz > tcg-hub-release.tar.gz.sha256)
reject --release "$tag2" --archive-sha256 "$signed_digest"
grep -Fq 'SHA-256' "$F/output"
mv "$arc.good" "$arc"; mv "$arc.sha256.good" "$arc.sha256"
reject --release "$tag2" --archive-sha256 invalid
cp "$F/config/access.env" "$F/config/local"; echo 'export PUBLIC_ORIGIN=https://cards.example.org' > "$F/config/access.env"
reject --release "$tag2"; mv "$F/config/local" "$F/config/access.env"
[[ $(count maintenance) == 0 && -f $F/running ]]
# A kill after publishing the backup reuses its verified copy. Another kill after the
# guest switch resumes the same release while the host completion marker is still old.
touch "$F/fail-after-backup"; reject --release "$tag2"
touch "$F/fail-install"; reject --release "$tag2"
[[ $(count backup-for-update) == 1 && $(count install) == 3 ]]
touch "$F/missing-game"; reject --release "$tag2"; rm "$F/missing-game"
run --release "$tag2" --archive-sha256 "$signed_digest"; run --release "$tag2"
[[ $(count backup-for-update) == 1 && $(count install) == 4 && $(count start-local) == 2 ]]
cmp "$F/userdata" "$HOME"/tcg-backups/*/db.dump
reject --release "$tag1"
[[ $(count install) == 4 && $(count backup-for-update) == 1 ]]
# A healthy completed but stopped installation starts without install/backup/maintenance.
rm "$F/running"; touch "$PREFIX/var/service/tcg-api/down" "$PREFIX/var/service/tcg-worker/down"
run --release "$tag2"; [[ $(count install) == 4 && $(count start-local) == 3 ]]
run --release "$tag3"; reject --release "$tag2"
[[ $(count install) == 5 && $(count backup-for-update) == 2 ]]
# Old releases may have a valid current tree and user data but no host completion marker.
tag4=a90-2026.11.25.11; bundle "$tag4"
rm "$PREFIX/var/lib/tcg-hub/installed-manifest" "$PREFIX/var/lib/tcg-hub/local-setup.release"
touch "$F/fail-install"; reject --release "$tag4"
run --release "$tag4"
[[ $(count install) == 7 && $(count backup-for-update) == 3 ]]
echo 'OK Termux mobile setup: private install, pinned recovery, no-op, stopped service, monotonic updates, verified backups, integrity and public protection.'
