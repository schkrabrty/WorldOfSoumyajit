#!/bin/bash
set -euo pipefail
preview_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
if [[ "${1:-}" == "--no-browser" ]]; then
    shift
else
    set -- --open-url "$@"
fi
echo "Previewing the built website at http://127.0.0.1:4000/"
echo "Keep this terminal open while editing. Press Control-C to stop."
exec /bin/bash "$preview_root/scripts/jekyll.sh" serve \
    --host 127.0.0.1 --port 4000 --livereload "$@"
