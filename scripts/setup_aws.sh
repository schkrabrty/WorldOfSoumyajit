#!/bin/bash
# Install AWS CLI 2 for this project's local manager, without system changes.
set -euo pipefail
storage_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
mkdir -p "$storage_root/.site-manager"
storage_installer="$storage_root/.site-manager/aws-cli-installer.sh"
curl --fail --silent --show-error --location https://awscli.amazonaws.com/v2/install.sh --output "$storage_installer"
XDG_DATA_HOME="$storage_root/.site-manager/aws-cli-data" \
XDG_BIN_HOME="$storage_root/.site-manager/aws-cli-bin" \
    bash "$storage_installer"
