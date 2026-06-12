#!/usr/bin/env bash
set -euo pipefail

tracked="$(git ls-files 'windmill/scripts/**' '*.windmill-export.py' 'windmill/deploy.py')"
if [[ -n "${tracked}" ]]; then
  echo "Tracked Windmill mirror files are not allowed:"
  printf '%s\n' "${tracked}"
  exit 1
fi
