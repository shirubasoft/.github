#!/usr/bin/env bash
set -euo pipefail
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
curl --fail --silent --show-error --location \
  https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_linux_amd64.tar.gz \
  --output "$stage/actionlint.tar.gz"
# Release digest is pinned alongside the version.
printf '%s  %s\n' 023070a287cd8cccd71515fedc843f1985bf96c436b7effaecce67290e7e0757 "$stage/actionlint.tar.gz" | sha256sum --check --status
tar -xzf "$stage/actionlint.tar.gz" -C "$stage" actionlint
"$stage/actionlint" -color .github/workflows/*.yml
if [[ -d workflow-templates ]]; then
  "$stage/actionlint" -color workflow-templates/*.yml
fi
