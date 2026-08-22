#!/bin/bash
# THE EXTENSION SURFACE, REPEATEDLY. Deterministic suites are cheap, so the
# only reason to run them once is habit.
#
#   sh proof/extension_campaign.sh 5
#
# Repetition here is not about flakiness in the assertions — these are offline
# and deterministic — it is about ORDERING and SHARED STATE. run_all.mjs runs
# 44 suites in one process each, but chrome_mock.mjs installs a global `chrome`
# and several suites patch storage.session in themselves; a suite that leaks
# state only shows up when the set is run again straight afterwards, and a suite
# that depends on being run first only shows up when something else changes.
#
# The python suite is included because tests/ source-scans the extension: a
# change to agent_loop.js can break test_agent_model_proxy_security.py or
# test_earls_live_failures.py without touching a single .mjs file.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
RIG="${ANTICIPY_RIG_DIR:-$HOME/.anticipy-rig}"
PASSES="${1:-5}"
cd "$REPO"

ext_fail=0; py_fail=0; fx_fail=0
for i in $(seq 1 "$PASSES"); do
  echo "=================== extension pass $i/$PASSES ==================="

  if node extension/tests/run_all.mjs > "/tmp/ext_pass$i.log" 2>&1; then
    echo "  offline suites   $(grep -c '^PASS' "/tmp/ext_pass$i.log") assertions, all 44 suites passed"
  else
    echo "  offline suites   FAILED"; grep -E '^FAIL|failed' "/tmp/ext_pass$i.log" | head -5
    ext_fail=$((ext_fail+1))
  fi

  if "$RIG/venv/bin/python" -m pytest tests/ -q \
        --ignore=tests/test_day_zero_oracle.py > "/tmp/py_pass$i.log" 2>&1; then
    echo "  python suite     $(tail -1 "/tmp/py_pass$i.log")"
  else
    echo "  python suite     FAILED"; tail -4 "/tmp/py_pass$i.log"
    py_fail=$((py_fail+1))
  fi

  # The fixture web is the oracle every browser task is graded against. If its
  # bytes move, every battery result in the same window is unreadable.
  if sh proof/fixtures/verify.sh > "/tmp/fx_pass$i.log" 2>&1; then
    echo "  fixture web      $(grep -oE '[0-9]+ passed, [0-9]+ failed' "/tmp/fx_pass$i.log" | tail -1)"
  else
    echo "  fixture web      FAILED"; tail -4 "/tmp/fx_pass$i.log"
    fx_fail=$((fx_fail+1))
  fi

  # Proves the row the battery writes is a row a real Chrome will run. Cheap,
  # no model calls, and it is the difference between measuring the agent and
  # measuring our own paperwork.
  if node proof/battery/selfcheck.mjs > "/tmp/sc_pass$i.log" 2>&1; then
    echo "  queue selfcheck  $(grep -c '^ *[0-9]*\. *PASS' "/tmp/sc_pass$i.log") checks passed"
  else
    echo "  queue selfcheck  FAILED"; tail -4 "/tmp/sc_pass$i.log"
  fi
done

echo ""
echo "extension campaign: $PASSES passes"
echo "  offline suite failures : $ext_fail"
echo "  python suite failures  : $py_fail"
echo "  fixture failures       : $fx_fail"
[ $((ext_fail+py_fail+fx_fail)) -eq 0 ] && echo "  every pass identical — no ordering or shared-state defect surfaced"
