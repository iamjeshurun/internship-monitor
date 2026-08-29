#!/bin/zsh
set -euo pipefail
PROJECT_DIR="${0:A:h:h}"
CONVERTER="$(xcrun --find safari-web-extension-converter 2>/dev/null || true)"
if [[ -z "$CONVERTER" ]]; then
  echo "Safari converter not found. Install and open the full Xcode app first." >&2
  exit 2
fi
exec "$CONVERTER" "$PROJECT_DIR/browser-extension" --project-location "$PROJECT_DIR/safari/generated" --app-name "Job Monitor Review Autofill" --bundle-identifier "com.jobmonitor.review-autofill"
