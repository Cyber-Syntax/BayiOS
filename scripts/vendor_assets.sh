#!/usr/bin/env bash
set -euo pipefail

HTMX_VERSION=2.0.4
ALPINE_VERSION=3.14.8

dest="$(git rev-parse --show-toplevel)/src/bayios/web/static/vendor"
mkdir -p "$dest"

curl -fsSL "https://unpkg.com/htmx.org@${HTMX_VERSION}/dist/htmx.min.js" -o "$dest/htmx.min.js"
curl -fsSL "https://unpkg.com/alpinejs@${ALPINE_VERSION}/dist/cdn.min.js" -o "$dest/alpine.min.js"

{
  echo "htmx ${HTMX_VERSION}"
  echo "alpinejs ${ALPINE_VERSION}"
  (cd "$dest" && sha256sum htmx.min.js alpine.min.js)
} >"$dest/VERSIONS.txt"

cat "$dest/VERSIONS.txt"
