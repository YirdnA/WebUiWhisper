#!/usr/bin/env bash
# WebUiWhisper — one-shot Apache + Let's Encrypt installer.
#
# Usage (from anywhere):
#   sudo bash /opt/webuiwhisper/scripts/install-apache.sh [username] [email]
#
# Defaults: username=chai, email=4685544@gmail.com
#
# What this does:
#   1. Verifies DNS for whisper.macroscop.org.
#   2. Installs the vhost template into /etc/apache2/sites-available/.
#   3. Creates /etc/apache2/.htpasswd-whisper (interactive password prompt).
#   4. Enables the site, validates Apache config, reloads.
#   5. Runs `certbot --apache` to acquire the cert and wire up :443.
#   6. Reloads and prints a quick health summary.
#
# Re-runnable: existing htpasswd file is preserved; existing cert is reused.

set -euo pipefail

USERNAME="${1:-chai}"
EMAIL="${2:-4685544@gmail.com}"
DOMAIN="whisper.macroscop.org"
VHOST_SRC="/opt/webuiwhisper/scripts/whisper.macroscop.org.conf"
VHOST_DST="/etc/apache2/sites-available/${DOMAIN}.conf"
HTPASSWD="/etc/apache2/.htpasswd-whisper"

if [ "${EUID}" -ne 0 ]; then
    echo "This script must run as root. Try: sudo bash $0 ${USERNAME} ${EMAIL}" >&2
    exit 1
fi

bold() { printf '\033[1m%s\033[0m\n' "$*"; }

bold "=== 1) DNS check ==="
ip="$(dig +short "${DOMAIN}" | head -1)"
if [ -z "${ip}" ]; then
    echo "FAIL: ${DOMAIN} does not resolve. Add the A record at Cloudflare first." >&2
    exit 1
fi
echo "OK: ${DOMAIN} -> ${ip}"

bold "=== 2) Install vhost template ==="
if [ ! -f "${VHOST_SRC}" ]; then
    echo "FAIL: ${VHOST_SRC} missing" >&2
    exit 1
fi
install -m 0644 -o root -g root "${VHOST_SRC}" "${VHOST_DST}"
echo "Installed: ${VHOST_DST}"

bold "=== 3) htpasswd for user '${USERNAME}' ==="
if [ -f "${HTPASSWD}" ] && grep -q "^${USERNAME}:" "${HTPASSWD}"; then
    echo "User '${USERNAME}' already exists in ${HTPASSWD}; leaving it alone."
    echo "To replace the password later: sudo htpasswd ${HTPASSWD} ${USERNAME}"
else
    if [ -f "${HTPASSWD}" ]; then
        htpasswd "${HTPASSWD}" "${USERNAME}"
    else
        htpasswd -c "${HTPASSWD}" "${USERNAME}"
    fi
    chown root:www-data "${HTPASSWD}"
    chmod 0640 "${HTPASSWD}"
    echo "htpasswd entry written for ${USERNAME}."
fi

bold "=== 4) Enable site + validate + reload ==="
a2ensite "${DOMAIN}.conf"
apache2ctl configtest
systemctl reload apache2
echo "Apache reloaded with vhost enabled."

bold "=== 5) Certbot --apache (HTTP-01 + redirect) ==="
certbot --apache \
    -d "${DOMAIN}" \
    --redirect \
    --agree-tos \
    -m "${EMAIL}" \
    --non-interactive

bold "=== 6) Final reload + health summary ==="
systemctl reload apache2
echo
echo "=== HTTP (should be 301 to HTTPS) ==="
curl -sI "http://${DOMAIN}/" | head -3 || true
echo
echo "=== HTTPS without auth (should be 401) ==="
curl -sI "https://${DOMAIN}/" | head -3 || true
echo
echo "=== HTTPS with bad auth (should be 401) ==="
curl -sI -u "${USERNAME}:wrong" "https://${DOMAIN}/" | head -3 || true
echo
echo "Done. To test in the browser: https://${DOMAIN}/"
echo "(Make sure your uvicorn is up on 127.0.0.1:8001 first.)"
