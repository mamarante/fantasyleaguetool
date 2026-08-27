#!/usr/bin/env bash
# Runs `nailer report` once, meant to be called from cron/launchd so the
# report refreshes daily without you having to remember to run it.
#
# The per-day API cache (cache.ttl_hours in config.yaml, default 24) means
# running this more than once a day just re-reads cached data, not fresh
# ESPN/Yahoo calls — daily is the natural cadence, not "every time a
# terminal opens."
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

source .venv/bin/activate
mkdir -p logs
nailer report >> "logs/cron-$(date +%F).log" 2>&1
