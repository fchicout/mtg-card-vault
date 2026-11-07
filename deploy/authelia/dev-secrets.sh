#!/usr/bin/env bash
# Generates the throwaway secrets of the development Authelia into ./secrets/ (git-ignored).
# Re-running keeps existing files; delete the directory to start over.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
mkdir -p secrets data
umask 077
rand() { openssl rand -hex 32; }
for name in session_secret storage_key reset_jwt_secret oidc_hmac; do
  [ -f "secrets/$name" ] || rand > "secrets/$name"
done
[ -f secrets/oidc.pem ] || openssl genrsa -out secrets/oidc.pem 2048 2>/dev/null
if [ ! -f secrets/tls.crt ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 -keyout secrets/tls.key -out secrets/tls.crt \
    -subj "/CN=auth.localtest.me" -addext "subjectAltName=DNS:auth.localtest.me,DNS:localhost" 2>/dev/null
fi
chmod 644 secrets/* # the container user must read them; the directory is local and git-ignored
echo "secrets ready in $(pwd)/secrets"
