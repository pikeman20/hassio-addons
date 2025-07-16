#!/bin/sh
set -e
#Only for /html and /js directories

# Apply robust ingress path rewrites to all frontend source files before build
# Match href/src/window.location with stricter attribute/value detection
for dir in /app/frontend/js /app/frontend/html; do
  find "$dir" -type f -exec sed -Ei '
    s|(<[^>]+href[[:space:]]*=[[:space:]]*["'\''"])/|\1./|g;
    s|(<[^>]+src[[:space:]]*=[[:space:]]*["'\''"])/|\1./|g;
    s|(window\.location[[:space:]]*=[[:space:]]*["'\''"])/|\1./|g;
    s|(["'\''"])/api/|\1./api/|g
  ' {} +
done
