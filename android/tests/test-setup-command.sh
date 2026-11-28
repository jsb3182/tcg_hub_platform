#!/usr/bin/env bash
# Exercise the exact clipboard command with a local, fixed-response download fixture.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/classes" "$work/bin" "$work/prefix/tmp"
cat > "$work/Probe.java" <<'JAVA'
package kr.tcghub.control;
class Probe {
    public static void main(String[] args) {
        System.out.print(SetupCommand.forHashes(args[0], args[1]));
    }
}
JAVA
javac --release 8 -d "$work/classes" "$root/src/kr/tcghub/control/SetupCommand.java" "$work/Probe.java"
cat > "$work/bin/curl" <<'SH'
#!/usr/bin/env bash
set -eu
[[ $# == 10 && $1 == --proto && $2 == '=https' && $3 == --proto-redir && $4 == '=https' &&
   $5 == -fL && $6 == --retry && $7 == 3 && $8 == 'https://github.com/jsb3182/tcg_hub_platform/releases/download/a90-2026.11.28.9/setup-termux.sh' &&
   $9 == -o ]] || exit 4
[[ ${DOWNLOAD_OK:-yes} == yes ]] || exit 7
cp "$RESPONSE" "${10}"
SH
chmod 700 "$work/bin/curl"
export PREFIX="$work/prefix" RESPONSE="$work/response" OBSERVED="$work/observed" PATH="$work/bin:$PATH"
printf '%s\n' '[[ $# == 4 && $1 == --release && $3 == --archive-sha256 && $4 == "$EXPECTED_ARCHIVE" ]] && printf "%s" "$2" > "$OBSERVED"' > "$RESPONSE"
hash=$(sha256sum "$RESPONSE" | cut -d' ' -f1)
export EXPECTED_ARCHIVE
EXPECTED_ARCHIVE=$(printf 'test archive' | sha256sum | cut -d' ' -f1)
command=$(java -cp "$work/classes" kr.tcghub.control.Probe "$hash" "$EXPECTED_ARCHIVE")
bash -c "$command"
[[ $(cat "$OBSERVED") == a90-2026.11.28.9 ]]
rm "$OBSERVED"
clean="$work/minimal"
mkdir "$clean"
for tool in bash cp curl mktemp rm; do
    printf '#!/bin/sh\nexec "%s" "$@"\n' "$(type -P "$tool")" > "$clean/$tool"
    chmod 700 "$clean/$tool"
done
export SHA_TOOL
SHA_TOOL=$(type -P sha256sum)
cat > "$clean/pkg" <<'SH'
#!/bin/sh
[ "$*" = 'install -y curl coreutils' ] || exit 5
printf '#!/bin/sh\nexec "%s" "$@"\n' "$SHA_TOOL" > "$PATH/sha256sum"
/bin/chmod 700 "$PATH/sha256sum"
SH
chmod 700 "$clean/pkg"
PATH="$clean" bash -c "$command"
[[ -x $clean/sha256sum && $(cat "$OBSERVED") == a90-2026.11.28.9 ]]
rm "$OBSERVED"
printf '\n# changed bytes\n' >> "$RESPONSE"
if bash -c "$command"; then echo 'Accepted changed bytes' >&2; exit 1; fi
if DOWNLOAD_OK=no bash -c "$command"; then echo 'Ignored failed download' >&2; exit 1; fi
[[ ! -e $OBSERVED && -z $(ls -A "$PREFIX/tmp") ]]
if java -cp "$work/classes" kr.tcghub.control.Probe invalid "$EXPECTED_ARCHIVE" >/dev/null 2>&1; then exit 1; fi
if java -cp "$work/classes" kr.tcghub.control.Probe "$hash" invalid >/dev/null 2>&1; then exit 1; fi
echo 'Host, release, helper checksum, failure handling and private cleanup passed.'
