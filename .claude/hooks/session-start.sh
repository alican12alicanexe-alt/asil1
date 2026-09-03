#!/bin/bash
set -euo pipefail
LOG=/tmp/ponytail-install.log

if ! claude plugin marketplace list 2>/dev/null | grep -q 'DietrichGebert/ponytail'; then
  timeout 180 claude plugin marketplace add DietrichGebert/ponytail >>"$LOG" 2>&1 || true
fi

if ! claude plugin list 2>/dev/null | grep -q 'ponytail@ponytail'; then
  timeout 180 claude plugin install ponytail@ponytail --yes >>"$LOG" 2>&1 || true
fi
exit 0
