#!/bin/sh
# Writes /tmp/runtime-config.json (served as /config.json) from the container environment, so one
# image serves every environment (issue #60). Values are restricted to URL-safe characters: a
# malformed setting stops the container instead of producing broken or injectable JSON.
set -eu

target=/tmp/runtime-config.json
csp_include=/tmp/idp-origin.conf
issuer="${OIDC_ISSUER_URL:-}"

if [ -z "$issuer" ]; then
  echo "runtime-config: OIDC_ISSUER_URL is not set; sign-in is disabled" >&2
  printf '{}\n' > "$target"
  printf 'map $host $idp_origin { default ""; }\n' > "$csp_include"
  exit 0
fi

client_id="${OIDC_CLIENT_ID:-}"
audience="${OIDC_AUDIENCE:-mtgvault-api}"

check() {
  case "$2" in
    "" | *[!A-Za-z0-9._:/@-]*)
      echo "runtime-config: $1 is empty or contains characters that are not allowed" >&2
      exit 1
      ;;
  esac
}
check OIDC_ISSUER_URL "$issuer"
check OIDC_CLIENT_ID "$client_id"
check OIDC_AUDIENCE "$audience"

printf '{"issuer":"%s","clientId":"%s","audience":"%s"}\n' "$issuer" "$client_id" "$audience" > "$target"

# The browser talks to the provider's token and discovery endpoints: its origin (and only that)
# is added to the CSP connect-src (included by nginx.conf, used in security-headers.conf).
origin="$(printf '%s' "$issuer" | sed -E 's#^(https?://[^/]+).*#\1#')"
printf 'map $host $idp_origin { default "%s"; }\n' "$origin" > "$csp_include"
