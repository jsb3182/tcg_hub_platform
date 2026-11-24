#!/usr/bin/env bash
# Shared by the guest installer, operator CLI and foreground tunnel process.
valid_public_settings() {
  local origin=${1:-} team=${2:-} aud=${3:-}
  local label='[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
  local host=${origin#https://}
  [[ $origin == https://* && ${#host} -le 253 && $host =~ ^($label\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ &&
     ${host,,} != *.localhost && $team =~ ^$label\.cloudflareaccess\.com$ && $aud =~ ^[[:xdigit:]]{64}$ ]]
}

write_access_settings() {
  local file
  file=$(mktemp "$config/access.XXXXXX")
  printf 'export PUBLIC_ORIGIN=%q\nexport CF_TEAM_DOMAIN=%q\nexport CF_AUDIENCE=%q\n' "$1" "$2" "$3" > "$file"
  # This file contains only public identifiers. The tunnel account never reads runtime.env.
  chmod 0644 "$file"
  mv -f "$file" "$config/access.env"
}

require_public_settings() {
  [[ -r $config/access.env ]] || { echo 'Run tcgctl configure-public first.' >&2; return 1; }
  source "$config/access.env"
  valid_public_settings "${PUBLIC_ORIGIN:-}" "${CF_TEAM_DOMAIN:-}" "${CF_AUDIENCE:-}" || {
    echo 'Public start requires an HTTPS hostname, Cloudflare Access team domain and application AUD.' >&2
    return 1
  }
}

public_origin_ready() {
  local origin=http://127.0.0.1:8080
  curl --noproxy '*' -fsS --max-time 4 "$origin/internal/ready" >/dev/null 2>&1 &&
    curl --noproxy '*' -fsS --max-time 4 "$origin/api/v1/auth/admin-mode" 2>/dev/null |
    python3 -c 'import json, sys; sys.exit(json.load(sys.stdin).get("mode") != "CLOUDFLARE")' 2>/dev/null
}

require_local_settings() {
  source "$config/access.env"
  [[ ${PUBLIC_ORIGIN:-} == http://127.0.0.1:8080 && -z ${CF_TEAM_DOMAIN:-} && -z ${CF_AUDIENCE:-} ]] || {
    echo 'Requires the A90 loopback-only installation.' >&2; return 1
  }
}

install_tunnel_package() {
  install -d -m 0755 /usr/share/keyrings
  curl --fail --silent --show-error --location https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
  chmod 0644 /usr/share/keyrings/cloudflare-main.gpg
  printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared noble main' > /etc/apt/sources.list.d/tcg-cloudflared.list
  chmod 0644 /etc/apt/sources.list.d/tcg-cloudflared.list
  apt-get update
  apt-get install -y --no-install-recommends cloudflared
}
