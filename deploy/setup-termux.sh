#!/data/data/com.termux/files/usr/bin/bash
# Install or resume a verified official release from inside arm64 Termux.
set -euo pipefail
umask 077
fail() { echo "$*" >&2; exit 1; }
valid_tag() { [[ $1 =~ ^a90-[0-9]{4}\.[0-9]{2}\.[0-9]{2}(\.[0-9]+)?$ ]]; }
tag= archive_pin=
if (( $# )); then
  [[ ( $# == 2 || $# == 4 ) && $1 == --release ]] && valid_tag "$2" ||
    fail 'Usage: bash setup-termux.sh [--release a90-YYYY.MM.DD.N [--archive-sha256 HEX]]'
  tag=$2
  if [[ $# == 4 ]]; then
    [[ $3 == --archive-sha256 && $4 =~ ^[a-f0-9]{64}$ ]] || fail 'Expected the lowercase SHA-256 from the signed app.'
    archive_pin=$4
  fi
fi
: "${PREFIX:?Open Termux on the A90 first}"
[[ $(uname -m) == aarch64 ]] || fail 'Requires arm64 Termux.'
packages=()
for pair in curl:curl sha256sum:coreutils tar:tar flock:util-linux; do
  command -v "${pair%:*}" >/dev/null || packages+=("${pair#*:}")
done
if (( ${#packages[@]} )); then pkg install -y "${packages[@]}"; fi
exec 9>"$HOME/.tcg-control.lock"
flock -n 9 || fail '다른 TCG 관리 작업이 진행 중입니다. 끝나면 다시 실행하세요.'
state="$PREFIX/var/lib/tcg-hub"
journal="$state/local-setup.pending"
saved="$state/installed-manifest"
finished="$state/local-setup.release"
pending_target= pending_base= pending_backup=
if [[ -e $journal ]]; then
  read -r pending_tag pending_target pending_base pending_backup extra < "$journal"
  valid_tag "$pending_tag" && [[ -z $extra && $pending_target =~ ^[a-f0-9]{20}$ &&
      ( $pending_base == - || $pending_base =~ ^[a-f0-9]{20}$ ) &&
      ( $pending_backup == - || $pending_backup =~ ^[0-9]{8}T[0-9]{6}Z-[0-9]+$ ) ]] || fail 'Invalid setup recovery record.'
  [[ -z $tag || $tag == "$pending_tag" ]] || fail "설치가 중단된 $pending_tag 버전으로 재개하세요. --release $pending_tag"
  tag=$pending_tag
fi
official=https://github.com/jsb3182/tcg_hub_platform/releases
download() { curl --proto '=https' --proto-redir '=https' --fail --silent --show-error --location --retry 3 "$@"; }
if [[ -z $tag ]]; then
  resolved=$(download --output /dev/null --write-out '%{url_effective}' "$official/latest")
  tag=${resolved#"$official/tag/"}
  [[ $resolved == "$official/tag/$tag" ]] && valid_tag "$tag" || fail 'Latest did not resolve to an official A90 release tag.'
fi
if [[ -e $finished ]]; then
  read -r last_tag last_id extra < "$finished"
  valid_tag "$last_tag" && [[ $last_id =~ ^[a-f0-9]{20}$ && -z $extra ]] || fail 'Invalid installed release record.'
  latest=$(printf '%s\n' "$last_tag" "$tag" | LC_ALL=C sort -V | tail -1)
  [[ $latest == "$tag" ]] || fail "이미 더 새 버전($last_tag)을 설치했습니다."
fi
work=$(mktemp -d "${TMPDIR:-$PREFIX/tmp}/tcg-setup.XXXXXX")
trap 'rm -rf -- "$work"' EXIT
archive=tcg-hub-release.tar.gz
release="$work/release"
echo "$tag 배포 파일을 확인하고 있습니다."
for asset in "$archive.sha256" bootstrap-termux.sh "$archive"; do
  download --output "$work/$asset" "$official/download/$tag/$asset"
done
mapfile -t lines < "$work/$archive.sha256"
[[ ${#lines[@]} == 1 ]] || fail 'Invalid release checksum file.'
read -r digest filename <<< "${lines[0]}"
[[ $digest =~ ^[[:xdigit:]]{64}$ && ${filename#\*} == "$archive" ]] || fail 'Invalid release checksum file.'
hash() { sha256sum "$1" | cut -d' ' -f1; }
actual=$(hash "$work/$archive")
[[ $actual == "${digest,,}" ]] || fail 'Release archive checksum mismatch.'
[[ -z $archive_pin || $actual == "$archive_pin" ]] || fail '배포 파일이 서명된 앱에 기록된 SHA-256과 일치하지 않습니다.'
mkdir "$release"
tar --no-same-owner -xzf "$work/$archive" -C "$release"
(cd "$release" && sha256sum --quiet --check MANIFEST.sha256)
for file in tcg-hub.jar deploy/setup-termux.sh deploy/bootstrap-termux.sh deploy/tcgctl; do
  [[ -s $release/$file ]] && grep -Eq "^[[:xdigit:]]{64} [ *]\./${file//./\\.}$" "$release/MANIFEST.sha256" ||
    fail "Release lacks a verified $file. Use an A90 release with mobile setup support."
done
[[ $(hash "$0") == "$(hash "$release/deploy/setup-termux.sh")" ]] || fail "Use setup-termux.sh from release $tag."
[[ $(hash "$work/bootstrap-termux.sh") == "$(hash "$release/deploy/bootstrap-termux.sh")" ]] || fail 'Bootstrap differs from verified release.'
id=$(hash "$release/MANIFEST.sha256" | cut -c1-20)
[[ -z $pending_target || $pending_target == "$id" ]] || fail 'The unfinished release changed. Keep the original recovery files.'
if [[ ${last_tag:-} == "$tag" && $last_id != "$id" ]]; then fail 'The installed tag now identifies different files.'; fi

packages=()
for pair in proot-distro:proot-distro sv:termux-services python:python; do
  command -v "${pair%:*}" >/dev/null || packages+=("${pair#*:}")
done
if (( ${#packages[@]} )); then pkg install -y "${packages[@]}" 9>&-; fi
guest() { proot-distro login ubuntu-tcg --isolated -- "$@"; }
if ! guest /bin/true >/dev/null 2>&1; then
  [[ ! -e $saved && ! -e $finished && ${pending_base:--} == - ]] || fail 'Existing Ubuntu could not be opened. Re-open it before upgrading.'
  proot-distro install ubuntu:24.04 --name ubuntu-tcg
fi
active=$(guest /bin/bash -se -- /etc/tcg-hub /opt/tcg-hub/current /var/lib/tcg-hub/restore-in-progress <<'GUEST'
config=$1 app=$2
[[ ! -e $3 ]] || { echo 'Complete the pending restore first.' >&2; exit 1; }
if [[ -e $config/runtime.env || -e $config/access.env || -L $app ]]; then
  unset PUBLIC_ORIGIN CF_TEAM_DOMAIN CF_AUDIENCE
  if [[ -f $config/runtime.env ]]; then source "$config/runtime.env"; fi
  if [[ -f $config/access.env ]]; then source "$config/access.env"; fi
  [[ ${PUBLIC_ORIGIN:-} == http://127.0.0.1:8080 && -z ${CF_TEAM_DOMAIN:-} && -z ${CF_AUDIENCE:-} ]] ||
    { echo '기존 공개 또는 사용자 지정 설정을 확인했습니다. 배포 가이드의 수동 업데이트 절차를 사용하세요.' >&2; exit 1; }
fi
if [[ -e $app || -L $app ]]; then
  dest=$(readlink -f "$app")
  [[ -s $app/MANIFEST.sha256 && -s $app/tcg-hub.jar && -f $app/.installed ]] || exit 1
  id=$(sha256sum "$app/MANIFEST.sha256" | cut -c1-20)
  [[ $dest == "${app%/*}/releases/$id" ]] || exit 1
  echo "$id"
else echo -; fi
GUEST
)
[[ $active == - || $active =~ ^[a-f0-9]{20}$ ]] || fail 'Unexpected Ubuntu release state.'
installed=-
if [[ -e $saved ]]; then
  read -r installed < "$saved"
  [[ $installed =~ ^[a-f0-9]{20}$ && $active != - ]] || fail 'The completed installation and active Ubuntu release disagree.'
fi
if [[ -n $pending_target ]]; then
  [[ ( $installed == - || $installed == "$pending_base" || $installed == "$id" ) &&
     ( $active == "$pending_base" || $active == "$id" ) ]] || fail 'Installation changed during the interrupted setup.'
elif [[ $installed != - && $active != "$installed" && $active != "$id" ]]; then
  fail 'A different upgrade is already partly installed. Resume that release first.'
elif [[ -f $finished && $installed != - && $installed != "$last_id" && $installed != "$id" ]]; then
  fail 'The active release was changed manually. Verify its version before continuing.'
fi
svroot="$PREFIX/var/service"
writers_down() {
  local member
  for member in api worker tunnel; do [[ -f $svroot/tcg-$member/down ]] || return 1; done
}
complete() {
  [[ $installed == "$id" && $active == "$id" ]] || return 1
  local member
  for member in db api worker tunnel; do [[ -x $svroot/tcg-$member/run ]] || return 1; done
}
ensure_supervisor() {
  local service="$svroot/tcg-$1" n
  if sv status "$service" >/dev/null 2>&1; then return 0; fi
  # A stale supervise/control FIFO can survive the Android process being killed.
  (exec 9>&-; bash "$HOME/.termux/boot/30-tcg-services")
  for (( n=0; n<30; n++ )); do
    if sv status "$service" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  fail "Service supervisor unavailable: tcg-$1"
}
record() { local tmp; tmp=$(mktemp "$1.XXXXXX"); printf '%s\n' "$2" > "$tmp"; mv -f "$tmp" "$1"; }
mkdir -p "$state"
export TCG_RELEASE_DIR="$release"
ctl() { bash "$release/deploy/tcgctl" "$@"; }
if ! complete; then
  base=${pending_base:-$installed}
  # An older active release without a completion marker can still contain user data.
  if [[ $base == - && $active != - && $active != "$id" ]]; then base=$active; fi
  if [[ $base == - && $active == "$id" ]]; then
    for member in api worker; do
      if [[ -x $svroot/tcg-$member/run && ! -f $svroot/tcg-$member/down ]]; then base=$active; fi
    done
  fi
  backup=${pending_backup:--}
  if [[ $base != - ]]; then
    # A manual restart after a previous backup may have produced new data.
    if [[ $backup == - ]] || { [[ -d $HOME/tcg-backups/$backup ]] && ! writers_down; }; then
      backup="$(date -u +%Y%m%dT%H%M%SZ)-$$"
    fi
  fi
  record "$journal" "$tag $id $base $backup"
  if [[ $backup != - ]]; then
    ensure_supervisor db
    ctl service-controls
    ctl maintenance
    writers_down || fail 'Writers are still enabled.'
    folder="$HOME/tcg-backups/$backup"
    if [[ ! -d $folder ]]; then ctl backup-for-update "$backup"; fi
    (cd "$folder"
     [[ -s db.dump && -s files.tar.gz && $(wc -l < SHA256SUMS) == 2 ]]
     for item in db.dump files.tar.gz; do
       grep -Eq "^[[:xdigit:]]{64} [ *]${item//./\\.}$" SHA256SUMS
     done
     sha256sum --quiet --check SHA256SUMS)
    echo "기존 데이터 백업 확인: $backup"
  fi
  ctl install --local
  [[ $(cat "$saved") == "$id" ]] || fail 'Installation did not finish. Run this setup again.'
fi
tmpctl=$(mktemp "$PREFIX/bin/.tcgctl.XXXXXX")
install -m 0700 "$release/deploy/tcgctl" "$tmpctl"
mv -f "$tmpctl" "$PREFIX/bin/tcgctl"
if [[ ! -x $svroot/tcg-mobile/run ]]; then bash "$release/deploy/install-mobile-control.sh"; fi
ensure_supervisor mobile
healthy=true
for member in db api worker; do
  if ! sv status "$svroot/tcg-$member" | grep -q '^run:'; then healthy=false; fi
done
base_url=http://127.0.0.1:8080
if [[ $healthy != true || ! -f $svroot/tcg-tunnel/down ]] ||
    ! curl --noproxy '*' -fsS --max-time 4 "$base_url/internal/ready" >/dev/null; then ctl start-local; fi
sv -w 30 up "$svroot/tcg-mobile"
curl --noproxy '*' -fsS --max-time 10 "$base_url/internal/ready" |
  python -c 'import json,sys; sys.exit(json.load(sys.stdin).get("status") != "UP")'
curl --noproxy '*' -fsS --max-time 10 "$base_url/api/v1/games" |
  python -c 'import json,sys; sys.exit(not {"YUGIOH","POKEMON","WEISS","NIVEL","RIFTBOUND"} <= {g["code"] for g in json.load(sys.stdin)})'
record "$finished" "$tag $id"
rm -f -- "$journal"
echo "$tag 설치가 완료되었습니다. 이 휴대폰에서 $base_url/ 을 여세요."
echo '자동 카드 수집 진행 확인: tcgctl media check-catalogs'
