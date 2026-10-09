#!/usr/bin/env bash
set -euo pipefail
[[ $# == 1 ]] || { echo 'Usage: install-aspire.sh DESTINATION' >&2; exit 1; }
destination=$1
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
curl --fail --silent --show-error --location \
  https://github.com/dotnet/aspire/releases/download/v13.6.1/aspire-cli-linux-x64-13.6.1.tar.gz \
  --output "$stage/aspire.tar.gz"
printf '%s  %s\n' f5498a1b30f894186a805c08798d9ca4f112dfc3b5f24ab0acef3f8aa5d009b8 "$stage/aspire.tar.gz" | sha256sum --check --status
mkdir -p "$destination"
tar -xzf "$stage/aspire.tar.gz" -C "$destination"
"$destination/aspire" --version
