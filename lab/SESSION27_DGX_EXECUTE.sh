#!/bin/bash
# SESSION 27 — DGX Spark Execution Script
# Run this on DGX via SSH. Each step is independent — run sequentially.
# Total time: ~2 hours (mostly waiting for Nemotron download)
#
# IMPORTANT: This script is for reference. Run commands one at a time.
# DO NOT run as a batch script (.sh execution is forbidden by Loop's rules).

echo "=== SESSION 27: DGX SPARK EXECUTION ==="
echo "Date: $(date)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Pull Nemotron-3-Super-120B via Ollama (~87GB, ~30-60 min)
# ─────────────────────────────────────────────────────────────────────────────
echo "Step 1: Pulling Nemotron-3-Super..."

# Free memory before pulling large model
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'

# Pull the model (Q4_K_M quantization, ~87GB)
ollama pull nemotron-3-super:120b

# Verify it's loaded
ollama list | grep nemotron

# Quick test - verify it responds
echo "Testing Nemotron response..."
ollama run nemotron-3-super:120b "What is 2+2? Answer in one word." --verbose 2>&1 | tail -5

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Verify Ollama accessibility from containers
# ─────────────────────────────────────────────────────────────────────────────
echo "Step 2: Verifying Ollama accessibility..."

# Check Ollama listens on all interfaces
curl -s http://172.17.0.1:11434/api/tags | python3 -m json.tool | head -20

# If Ollama only listens on localhost, fix it:
# sudo systemctl edit ollama.service
# Add on line 3: [Service]\nEnvironment="OLLAMA_HOST=0.0.0.0"
# Then: sudo systemctl daemon-reload && sudo systemctl restart ollama

# Test tool calling capability
curl -s http://localhost:11434/api/chat -d '{
  "model": "nemotron-3-super:120b",
  "messages": [{"role":"user","content":"Read the file test.txt"}],
  "tools": [{"type":"function","function":{"name":"read_file","description":"Read a file from disk","parameters":{"type":"object","properties":{"path":{"type":"string","description":"File path"}}}}}],
  "stream": false
}' | python3 -m json.tool | head -30

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Configure OpenClaw heartbeat model routing
# ─────────────────────────────────────────────────────────────────────────────
echo "Step 3: Configuring OpenClaw model routing..."

# The critical config changes for ~/.openclaw/openclaw.json:
# 1. lightContext: true (collapses heartbeat tokens 200K -> 5K)
# 2. isolatedSession: true (don't pollute main context)
# 3. heartbeat model: nemotron-3-super:120b via Ollama
#
# Use openclaw config set commands or edit the JSON directly.
# The exact config format depends on your OpenClaw version.
#
# Key settings to add/modify in openclaw.json:
cat << 'CONFIG_EOF'

Add these to your openclaw.json agent configuration:

{
  "heartbeat": {
    "every": "30m",
    "lightContext": true,
    "isolatedSession": true
  }
}

For model routing, check if your OpenClaw version supports:
- Per-heartbeat model override
- Or use the escalateModel pattern

If native routing isn't supported, the lightContext + isolatedSession
alone will cut heartbeat costs by 40x even on Opus.

CONFIG_EOF

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Git sync + restart scanner with new code
# ─────────────────────────────────────────────────────────────────────────────
echo "Step 4: Syncing code and restarting scanner..."

cd /opt/loop

# Pull latest changes (Session 27 fixes)
git fetch origin && git reset --hard origin/main

# Verify tests pass on DGX
.venv/bin/python3 -m pytest tests/ --tb=short -k 'not test_api' -q

# Restart scanner to pick up meta-gate + staleness detection
echo "restart requested $(date)" > lab/.restart-scanner

# Wait for restart
sleep 10
cat lab/.restart-scanner-log 2>/dev/null | tail -3

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Verify accuracy diagnosis
# ─────────────────────────────────────────────────────────────────────────────
echo "Step 5: Verifying base rate predictor..."

cd /opt/loop
.venv/bin/python3 -c "
from lab.base_rate_predictor import BaseRatePredictor
p = BaseRatePredictor.from_outcomes()
print(p.summary())
print()
# Critical check: does 556108 return Bearish?
result = p.predict('556108')
print(f'556108 prediction: {result.direction} @ {result.confidence:.0%}')
print(f'  Reasoning: {result.reasoning}')
if result.direction == 'Bullish':
    print('  BUG CONFIRMED: Base rate returning Bullish for bearish market!')
elif result.direction == 'Bearish':
    print('  CORRECT: Base rate returns Bearish (matches 94% trend)')
"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Check meta-gate and scanner behavior
# ─────────────────────────────────────────────────────────────────────────────
echo "Step 6: Checking meta-gate..."

# Check if meta-gate will fire (accuracy below 40%)
.venv/bin/python3 -c "
from lab.outcome_tracker import OutcomeState
from pathlib import Path
state = OutcomeState.load(Path('/opt/loop/data/prediction_outcomes.json'))
s = state.stats
print(f'Total predictions: {s[\"total_predictions\"]}')
print(f'Evaluated: {s[\"total_evaluated\"]}')
print(f'Correct: {s[\"correct\"]}')
print(f'Incorrect: {s[\"incorrect\"]}')
if s['correct'] + s['incorrect'] > 0:
    acc = s['correct'] / (s['correct'] + s['incorrect'])
    print(f'Accuracy: {acc:.1%}')
    if acc < 0.40:
        print('META-GATE WILL FIRE: Accuracy below 40%')
        print('Predictions will be halted until accuracy improves.')
        print('To override: set META_GATE_ACCURACY_FLOOR lower in masterloop.py')
"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Archive dead code
# ─────────────────────────────────────────────────────────────────────────────
echo "Step 7: Archiving dead code..."

mkdir -p /opt/loop/lab/archive
# Only archive if files exist and aren't already archived
[ -f /opt/loop/lab/langsmith_eval.py ] && mv /opt/loop/lab/langsmith_eval.py /opt/loop/lab/archive/
[ -f /opt/loop/lab/moltbook_register.py ] && mv /opt/loop/lab/moltbook_register.py /opt/loop/lab/archive/

echo ""
echo "=== SESSION 27 EXECUTION COMPLETE ==="
echo "Next steps:"
echo "  1. Verify scanner restarted with meta-gate active"
echo "  2. Check Loop's next heartbeat for structured format"
echo "  3. Monitor accuracy — if meta-gate halts predictions, consider retrain"
echo "  4. NemoClaw pilot: next week (after accuracy stabilizes)"
