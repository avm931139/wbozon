#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install-dashboard.sh [username]" >&2
  exit 1
fi

DASHBOARD_USER="${1:-anton}"
PROJECT_DIR="/home/wbozon/wbozon"

if ! ip -4 address show dev tun0 | grep -q '10\.8\.0\.1/24'; then
  echo "OpenVPN address 10.8.0.1/24 is absent on tun0; nothing was changed." >&2
  exit 1
fi

apt-get update
apt-get install -y nginx apache2-utils

install -d -m 700 /etc/nginx/ssl
if [[ ! -s /etc/nginx/ssl/wbozon-dashboard.key || ! -s /etc/nginx/ssl/wbozon-dashboard.crt ]]; then
  openssl req -x509 -nodes -newkey rsa:3072 -days 825 \
    -keyout /etc/nginx/ssl/wbozon-dashboard.key \
    -out /etc/nginx/ssl/wbozon-dashboard.crt \
    -subj '/CN=10.8.0.1' -addext 'subjectAltName=IP:10.8.0.1'
  chmod 600 /etc/nginx/ssl/wbozon-dashboard.key
fi

if [[ ! -s /etc/nginx/.htpasswd-wbozon-dashboard ]]; then
  echo "Create the dashboard password for user ${DASHBOARD_USER}:"
  htpasswd -c /etc/nginx/.htpasswd-wbozon-dashboard "${DASHBOARD_USER}"
fi

install -m 644 "${PROJECT_DIR}/deploy/nginx/wbozon-dashboard.conf" \
  /etc/nginx/sites-available/wbozon-dashboard
if [[ -e /etc/nginx/sites-enabled/wbozon-dashboard || -L /etc/nginx/sites-enabled/wbozon-dashboard ]]; then
  if [[ "$(readlink -f /etc/nginx/sites-enabled/wbozon-dashboard)" != "/etc/nginx/sites-available/wbozon-dashboard" ]]; then
    echo "Unexpected existing dashboard virtual host; refusing to overwrite it." >&2
    exit 1
  fi
else
  ln -s /etc/nginx/sites-available/wbozon-dashboard \
    /etc/nginx/sites-enabled/wbozon-dashboard
fi

# A fresh Debian/Ubuntu package exposes a placeholder on port 80. Remove only
# that verified package symlink; never touch any other Nginx virtual host.
if [[ -L /etc/nginx/sites-enabled/default ]] && \
   [[ "$(readlink -f /etc/nginx/sites-enabled/default)" == "/etc/nginx/sites-available/default" ]]; then
  unlink /etc/nginx/sites-enabled/default
fi

install -d /etc/systemd/system/nginx.service.d
install -m 644 "${PROJECT_DIR}/deploy/systemd/nginx.service.d/wbozon-dashboard.conf" \
  /etc/systemd/system/nginx.service.d/wbozon-dashboard.conf
install -m 644 "${PROJECT_DIR}/deploy/systemd/wbozon-dashboard.service" \
  /etc/systemd/system/wbozon-dashboard.service

systemctl daemon-reload
nginx -t
systemctl enable --now wbozon-dashboard.service
systemctl enable --now nginx.service

curl --fail --silent http://127.0.0.1:17843/health
echo
echo "Dashboard installed: https://10.8.0.1:28443"
echo "Connect to OpenVPN first; the TLS certificate is self-signed."
