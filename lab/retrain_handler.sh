#!/bin/bash
# lab/retrain_handler.sh — Trigger-file handler for XGBoost retrain
# Same pattern as .restart-scanner and .git-push-request handlers.
#
# Watched by systemd path unit: polysignal-retrain.path
# When lab/.retrain-trigger appears:
#   1. Run retrain pipeline
#   2. If model replaced: restart scanner to load new model
#   3. Write result to lab/.retrain-result
#   4. Remove trigger file

TRIGGER="/opt/loop/lab/.retrain-trigger"
RESULT="/opt/loop/lab/.retrain-result"
VENV="/opt/loop/.venv/bin/python3"

if [ ! -f "$TRIGGER" ]; then
    exit 0
fi

echo "$(date): Retrain triggered" > "$RESULT"
rm -f "$TRIGGER"

# Run retrain pipeline
cd /opt/loop
OUTPUT=$($VENV -m lab.retrain_pipeline 2>&1)
EXIT_CODE=$?

echo "$OUTPUT" >> "$RESULT"

if [ $EXIT_CODE -ne 0 ]; then
    echo "$(date): Retrain FAILED (exit $EXIT_CODE)" >> "$RESULT"
    exit 1
fi

# If model was replaced, restart scanner to load it
if echo "$OUTPUT" | grep -q "REPLACED"; then
    echo "$(date): Model replaced — restarting scanner..." >> "$RESULT"
    systemctl --user restart polysignal-scanner.service
    echo "$(date): Scanner restarted with new model" >> "$RESULT"
fi

echo "$(date): Retrain complete" >> "$RESULT"
