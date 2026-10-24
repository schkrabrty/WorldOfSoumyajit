#!/bin/bash
# Double-click this file on macOS to preview the complete website.
set -euo pipefail
preview_root="$(cd -- "$(dirname -- "$0")" && pwd)"
exec /bin/bash "$preview_root/scripts/preview_site.sh" "$@"
