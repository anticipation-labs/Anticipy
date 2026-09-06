#!/bin/sh
# Runs every test file under spike/two-hands/test/.
#
# WHY THIS FILE EXISTS: until 2026-09-06 nothing ran them. Seventeen files, no
# package.json, no runner, no gate leg — and one of them had gone red without
# anybody being able to know. See research/2026-09-06-spike-fence-expired.md.
#
# There is no `npm test` here on purpose: the spike's own fence forbids it a
# node_modules, so the runner is a shell loop over `node --experimental-strip-types`.
#
# Exits 0 only when EVERY file exits 0. A file that cannot be run at all counts
# as a failure, not as a skip — a suite that could not run is not a quiet pass.

set -u
cd "$(dirname "$0")" || exit 1

pass=0
fail=0
failed_files=""

for f in test/*.test.ts; do
  [ -e "$f" ] || { echo "no test files found under $(pwd)/test/"; exit 1; }
  if node --experimental-strip-types "$f" >/tmp/spike_test_out.$$ 2>&1; then
    pass=$((pass + 1))
    printf '  ok   %s\n' "$f"
  else
    fail=$((fail + 1))
    failed_files="$failed_files $f"
    printf '  FAIL %s\n' "$f"
    sed -n '1,40p' /tmp/spike_test_out.$$ | sed 's/^/       /'
  fi
  rm -f /tmp/spike_test_out.$$
done

echo
echo "spike/two-hands: $pass file(s) passed, $fail failed"
if [ "$fail" -ne 0 ]; then
  echo "failed:$failed_files"
  exit 1
fi
exit 0
