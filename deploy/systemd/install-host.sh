#!/usr/bin/env bash
# Installs a verified release into a native, systemd-managed Linux host.
set -euo pipefail
[[ $EUID == 0 && -d /run/systemd/system ]] || { echo 'Run as root on a systemd host.' >&2; exit 1; }
release=$(cd "$(dirname "$0")/../.." && pwd)
cd "$release"
sha256sum --quiet --check MANIFEST.sha256
[[ -s /etc/tcg-hub/host.env && -s /etc/tcg-hub/worker.env ]] || { echo 'Create /etc/tcg-hub/{host,worker}.env first. See deploy/systemd/README.md.' >&2; exit 2; }
for file in /etc/tcg-hub/{host,worker}.env; do
  [[ ! -L $file && $(stat -c '%u:%a' "$file") == 0:600 ]] || { echo "Requires root:0600 $file." >&2; exit 2; }
done
getent group tcg-files >/dev/null || groupadd --system tcg-files
for account in tcg-api tcg-worker; do
  id "$account" >/dev/null 2>&1 || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$account"
  usermod -a -G tcg-files "$account"
done
# The API receives the socket's group as a supplementary group even though its primary unit group is tcg-files.
install -d -m 0755 /opt/tcg-hub/releases /usr/local/libexec/tcg-hub
install -d -m 2770 -o root -g tcg-files /var/lib/tcg-hub /var/lib/tcg-hub/{media,spool}
install -d -m 0700 -o tcg-worker -g tcg-files /var/lib/tcg-hub/{models,catalog-cache}
digest=$(sha256sum MANIFEST.sha256 | cut -c1-20)
dest="/opt/tcg-hub/releases/$digest"
if [[ ! -f "$dest/.installed" ]]; then
  install -d -m 0755 "$dest"
  cp -R tcg-hub.jar crawler-middleware deploy docs MANIFEST.sha256 "$dest/"
  (cd "$dest" && sha256sum --quiet --check MANIFEST.sha256)
  python3 -m venv "$dest/venv"
  "$dest/venv/bin/pip" install --no-cache-dir --only-binary=:all: -r "$dest/crawler-middleware/requirements.txt"
  chmod -R a+rX "$dest"
  touch "$dest/.installed"
fi
python3 "$dest/deploy/install-translation-model.py" --destination /var/lib/tcg-hub/models/m2m100-418m-int8
chown -R tcg-worker:tcg-files /var/lib/tcg-hub/models
install -m 0644 deploy/systemd/host-control.py /usr/local/libexec/tcg-hub/
install -m 0644 deploy/systemd/*.service deploy/systemd/*.socket /etc/systemd/system/
ln -sfn "$dest" /opt/tcg-hub/current.next
mv -Tf /opt/tcg-hub/current.next /opt/tcg-hub/current
systemctl daemon-reload
systemctl enable tcg-hub-control.socket tcg-hub-api.service
systemctl start tcg-hub-control.socket
systemctl restart tcg-hub-api.service
