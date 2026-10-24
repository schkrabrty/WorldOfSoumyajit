#!/bin/bash
# Build shared templates before serving pages, and rebuild when files change.
set -euo pipefail
shopt -s nullglob

preview_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$preview_root"

preview_ruby=""
for candidate in \
    "$(command -v ruby || true)" \
    /opt/homebrew/opt/ruby@3.4/bin/ruby \
    /usr/local/opt/ruby@3.4/bin/ruby \
    /opt/homebrew/Library/Homebrew/vendor/portable-ruby/3.4.*/bin/ruby \
    /usr/local/Homebrew/Library/Homebrew/vendor/portable-ruby/3.4.*/bin/ruby; do
    if [[ -x "$candidate" ]] && "$candidate" -e 'exit(RUBY_VERSION.start_with?("3.4.") ? 0 : 1)'; then
        preview_ruby="$candidate"
        break
    fi
done
if [[ -z "$preview_ruby" ]]; then
    echo "Ruby 3.4 is needed for this website. Install it with: brew install ruby@3.4" >&2
    exit 1
fi

# Keep preview dependencies inside ignored project folders, not system Ruby.
export PATH="$(dirname "$preview_ruby"):$PATH"
export GEM_HOME="$preview_root/.bundle/preview/gems"
export GEM_PATH="$GEM_HOME"
export BUNDLE_PATH="$preview_root/vendor/bundle"
export BUNDLE_GEMFILE="$preview_root/Gemfile"
preview_bundler_version="$("$preview_ruby" -e 'puts File.read("Gemfile.lock")[/BUNDLED WITH\n\s+(\S+)/, 1]')"
preview_bundle="$GEM_HOME/gems/bundler-$preview_bundler_version/exe/bundle"
if [[ ! -f "$preview_bundle" ]]; then
    "$preview_ruby" "$(dirname "$preview_ruby")/gem" install bundler --version "$preview_bundler_version" --no-document
fi
if ! "$preview_ruby" "$preview_bundle" check >/dev/null 2>&1; then
    "$preview_ruby" "$preview_bundle" install
fi

exec "$preview_ruby" "$preview_bundle" exec jekyll "$@"
