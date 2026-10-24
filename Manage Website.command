#!/bin/bash
set -euo pipefail
manager_root="$(cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$manager_root/scripts/manage_site.py" "$@"
