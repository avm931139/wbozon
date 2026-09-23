#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install-dashboard-ca.sh [linux-user]" >&2
  exit 1
fi

DASHBOARD_LINUX_USER="${1:-wbozon}"
DASHBOARD_LINUX_GROUP="$(id -gn "${DASHBOARD_LINUX_USER}" 2>/dev/null || true)"
SSL_DIR="/etc/nginx/ssl"
CA_KEY="${SSL_DIR}/wbozon-dashboard-ca.key"
CA_CERT="${SSL_DIR}/wbozon-dashboard-ca.crt"
SERVER_KEY="${SSL_DIR}/wbozon-dashboard.key"
SERVER_CERT="${SSL_DIR}/wbozon-dashboard.crt"
EXPORT_CERT="/home/${DASHBOARD_LINUX_USER}/wbozon-dashboard-ca.crt"

if ! getent passwd "${DASHBOARD_LINUX_USER}" >/dev/null; then
  echo "Linux user does not exist: ${DASHBOARD_LINUX_USER}" >&2
  exit 1
fi
if [[ -z "${DASHBOARD_LINUX_GROUP}" ]]; then
  echo "Cannot determine primary group for ${DASHBOARD_LINUX_USER}." >&2
  exit 1
fi
if ! ip -4 address show dev tun0 | grep -q '10\.8\.0\.1/24'; then
  echo "OpenVPN address 10.8.0.1/24 is absent on tun0; nothing was changed." >&2
  exit 1
fi
if [[ ! -f /etc/nginx/sites-enabled/wbozon-dashboard ]]; then
  echo "Dashboard Nginx configuration is not enabled; nothing was changed." >&2
  exit 1
fi

install -d -o root -g root -m 700 "${SSL_DIR}"
WORK_DIR="$(mktemp -d /tmp/wbozon-dashboard-ca.XXXXXX)"
trap 'rm -rf -- "${WORK_DIR}"' EXIT

# A CA key is created once and remains root-only. Refuse an incomplete CA pair
# instead of silently replacing the trust anchor already installed on clients.
if [[ -e "${CA_KEY}" || -e "${CA_CERT}" ]]; then
  if [[ ! -s "${CA_KEY}" || ! -s "${CA_CERT}" ]]; then
    echo "Incomplete internal CA pair in ${SSL_DIR}; refusing to replace it." >&2
    exit 1
  fi
  cp -- "${CA_KEY}" "${WORK_DIR}/ca.key"
  cp -- "${CA_CERT}" "${WORK_DIR}/ca.crt"
else
  openssl req -x509 -newkey rsa:4096 -sha256 -nodes -days 3650 \
    -keyout "${WORK_DIR}/ca.key" -out "${WORK_DIR}/ca.crt" \
    -subj '/CN=wbozon Dashboard Internal CA' \
    -addext 'basicConstraints=critical,CA:TRUE' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign' \
    -addext 'subjectKeyIdentifier=hash'
fi

openssl req -new -newkey rsa:3072 -sha256 -nodes \
  -keyout "${WORK_DIR}/server.key" -out "${WORK_DIR}/server.csr" \
  -subj '/CN=10.8.0.1'
cat >"${WORK_DIR}/server.ext" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:10.8.0.1
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF
openssl x509 -req -in "${WORK_DIR}/server.csr" \
  -CA "${WORK_DIR}/ca.crt" -CAkey "${WORK_DIR}/ca.key" \
  -set_serial "0x$(openssl rand -hex 16)" -days 397 -sha256 \
  -extfile "${WORK_DIR}/server.ext" -out "${WORK_DIR}/server.crt"

openssl verify -CAfile "${WORK_DIR}/ca.crt" "${WORK_DIR}/server.crt"
openssl x509 -in "${WORK_DIR}/server.crt" -noout -ext subjectAltName \
  | grep -q 'IP Address:10\.8\.0\.1'

BACKUP_DIR="$(mktemp -d "${SSL_DIR}/dashboard-cert-backup.XXXXXX")"
chmod 700 "${BACKUP_DIR}"
[[ -f "${SERVER_KEY}" ]] && cp -a -- "${SERVER_KEY}" "${BACKUP_DIR}/"
[[ -f "${SERVER_CERT}" ]] && cp -a -- "${SERVER_CERT}" "${BACKUP_DIR}/"

install -o root -g root -m 600 "${WORK_DIR}/ca.key" "${CA_KEY}"
install -o root -g root -m 644 "${WORK_DIR}/ca.crt" "${CA_CERT}"
install -o root -g root -m 600 "${WORK_DIR}/server.key" "${SERVER_KEY}"
install -o root -g root -m 644 "${WORK_DIR}/server.crt" "${SERVER_CERT}"

if ! nginx -t; then
  echo "Nginx validation failed; restoring the previous dashboard certificate." >&2
  if [[ -f "${BACKUP_DIR}/wbozon-dashboard.key" && -f "${BACKUP_DIR}/wbozon-dashboard.crt" ]]; then
    install -o root -g root -m 600 "${BACKUP_DIR}/wbozon-dashboard.key" "${SERVER_KEY}"
    install -o root -g root -m 644 "${BACKUP_DIR}/wbozon-dashboard.crt" "${SERVER_CERT}"
  fi
  exit 1
fi

systemctl reload nginx.service
install -o "${DASHBOARD_LINUX_USER}" -g "${DASHBOARD_LINUX_GROUP}" -m 644 \
  "${CA_CERT}" "${EXPORT_CERT}"

echo "Internal CA installed. OpenVPN was not restarted."
echo "Public CA certificate for the client: ${EXPORT_CERT}"
openssl x509 -in "${CA_CERT}" -noout -fingerprint -sha1
openssl x509 -in "${CA_CERT}" -noout -fingerprint -sha256
echo "Dashboard: https://10.8.0.1:28443"
echo "Previous server certificate backup: ${BACKUP_DIR}"
