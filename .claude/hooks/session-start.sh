#!/bin/bash
# Install the understand-anything plugin so cloud sessions get its skills and agents.
# Idempotent and non-fatal: a failure here must never block session startup.
set -uo pipefail

PLUGIN_ID="understand-anything@understand-anything"
MARKETPLACE_REPO="Egonex-AI/Understand-Anything"

command -v claude >/dev/null 2>&1 || exit 0

if claude plugin list 2>/dev/null | grep -q "$PLUGIN_ID"; then
  exit 0
fi

claude plugin marketplace add "$MARKETPLACE_REPO" >/dev/null 2>&1
claude plugin install "$PLUGIN_ID" >/dev/null 2>&1

exit 0
