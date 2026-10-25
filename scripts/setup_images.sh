#!/bin/bash
# Keep image dependencies in this project's ignored cache, not system Python.
set -euo pipefail
images_source="$(cd -- "$(dirname -- "$0")" && pwd)"
images_root="${1:-$(dirname "$images_source")}"
images_python="${2:-python3}"
images_environment="$images_root/.site-manager/images-venv"
"$images_python" -m venv "$images_environment"
"$images_environment/bin/python3" -m pip install --disable-pip-version-check -r "$images_source/requirements-images.txt"
touch "$images_environment/.ready"
