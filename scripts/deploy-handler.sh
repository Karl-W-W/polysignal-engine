#!/bin/bash
# Triggered by: echo "deploy" > /opt/loop/lab/.deploy-trigger
# Pulls latest code from main, runs tests, restarts scanner if tests pass.
# Loop writes the trigger file from sandbox; this runs on host.
#
# Versioned here since 2026-09-10 (it lived only on the host before; installed at
# /opt/loop/scripts/deploy-handler.sh, which `git reset --hard origin/main` below now keeps current).
# The test run deselects @network tests: the full suite hung twice on 2026-09-08 on an external socket
# (tests/test_masterloop_e2e.py, see its pytestmark), so the handler never restarted the scanner and every
# deploy needed a hand. Karl's word 2026-09-10: marker, not a timeout. CI still runs those tests.

set -e
cd /opt/loop

echo "[DEPLOY] $(date) — Starting deploy..."

# Pull latest
git fetch origin
git reset --hard origin/main
echo "[DEPLOY] Code synced to $(git log --oneline -1)"

# Run tests
echo "[DEPLOY] Running tests..."
TEST_OUTPUT=$(.venv/bin/python3 -m pytest tests/ --tb=short -k "not test_api" -m "not network" -q -p no:cacheprovider 2>&1)
TEST_EXIT=$?
echo "$TEST_OUTPUT" | tail -5

if [ $TEST_EXIT -ne 0 ]; then
    echo "[DEPLOY] TESTS FAILED — aborting deploy"
    echo "FAILED: tests did not pass" > /opt/loop/lab/.deploy-result
    exit 1
fi

# Restart scanner
systemctl --user restart polysignal-scanner.service
sleep 5

# Verify
STATUS=$(systemctl --user is-active polysignal-scanner.service)
echo "[DEPLOY] Scanner status: $STATUS"
echo "SUCCESS: deployed $(git log --oneline -1), scanner $STATUS" > /opt/loop/lab/.deploy-result
echo "[DEPLOY] Complete"
