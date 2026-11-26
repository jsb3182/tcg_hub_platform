#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/frontend" "$tmp/backend" "$tmp/release/crawler-middleware" "$root/dist"

publish_file() (
  destination=$2
  partial=$(mktemp "$(dirname "$destination")/.$(basename "$destination").XXXXXX")
  trap 'rm -f -- "$partial"' EXIT
  cp "$1" "$partial"
  # A same-directory rename either replaces the name or fails if a Windows reader locks it.
  node -e 'require("node:fs").renameSync(process.argv[1], process.argv[2])' "$partial" "$destination"
)

tar -C "$root/frontend" --exclude='./node_modules' --exclude='./dist' -cf - . | tar -C "$tmp/frontend" -xf -
cd "$tmp/frontend"
if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
npm run build
test -s dist/index.html

cd "$root/backend"
cp -R pom.xml src "$tmp/backend/"
if [[ -d .mvn ]]; then cp -R .mvn "$tmp/backend/"; fi
if [[ -f mvnw ]]; then cp mvnw "$tmp/backend/"; fi
cd "$tmp/backend"
mkdir -p src/main/resources/static
cp -R "$tmp/frontend/dist/." src/main/resources/static/
if [[ -f mvnw ]]; then bash mvnw package; else mvn package; fi
test -s target/tcg-hub.jar
jar tf target/tcg-hub.jar | tr -d '\r' > "$tmp/jar-contents"
grep -Fxq 'BOOT-INF/classes/static/index.html' "$tmp/jar-contents"
grep -Eq '^BOOT-INF/classes/db/migration/V[^/]+\.sql$' "$tmp/jar-contents"
mkdir -p "$root/backend/target"
cp target/tcg-hub.jar "$tmp/release/"
cd "$root"
tar --exclude='__pycache__' --exclude='*.pyc' -cf - deploy | tar -C "$tmp/release" -xf -
cp crawler-middleware/requirements.txt crawler-middleware/README.md "$tmp/release/crawler-middleware/"
tar --exclude='__pycache__' --exclude='*.pyc' -C crawler-middleware -cf - tcg_worker | tar -C "$tmp/release/crawler-middleware" -xf -
mkdir -p "$tmp/release/docs"
cp docs/DEPLOYMENT.md docs/COLLECTION.md docs/CARD_SOURCES.md docs/ANDROID.md docs/STORES.md "$tmp/release/docs/"
cd "$tmp/release"
find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > "$tmp/MANIFEST.sha256"
cp "$tmp/MANIFEST.sha256" .
tar -czf "$tmp/tcg-hub-release.tar.gz" .
cd "$tmp"
sha256sum tcg-hub-release.tar.gz > tcg-hub-release.tar.gz.sha256
publish_file "$tmp/backend/target/tcg-hub.jar" "$root/backend/target/tcg-hub.jar"
publish_file tcg-hub-release.tar.gz "$root/dist/tcg-hub-release.tar.gz"
publish_file tcg-hub-release.tar.gz.sha256 "$root/dist/tcg-hub-release.tar.gz.sha256"
publish_file "$tmp/release/deploy/bootstrap-termux.sh" "$root/dist/bootstrap-termux.sh"
publish_file "$tmp/release/deploy/setup-termux.sh" "$root/dist/setup-termux.sh"
echo "Built $root/dist/tcg-hub-release.tar.gz"
