# OpenClaw Heartbeat Configuration — Session 27
# Apply to ~/.openclaw/openclaw.json on DGX
# After applying: systemctl --user restart openclaw-gateway.service

## What to Change

In the agent config section of openclaw.json, add/modify the heartbeat block:

```json
{
  "heartbeat": {
    "every": "30m",
    "lightContext": true,
    "isolatedSession": true
  }
}
```

### What Each Setting Does

- `lightContext: true` — Only injects HEARTBEAT.md instead of full bootstrap
  (200K tokens → 5K tokens per heartbeat = 40x cost reduction)
- `isolatedSession: true` — Heartbeat runs in its own session, doesn't
  pollute the main conversation context

### Model Routing (when Nemotron is available)

Once `ollama pull nemotron-3-super:120b` completes, update the model config:

```json
{
  "model": "anthropic/claude-opus-4-6",
  "heartbeat": {
    "every": "30m",
    "lightContext": true,
    "isolatedSession": true,
    "model": "ollama/nemotron-3-super:120b",
    "escalateModel": "anthropic/claude-opus-4-6"
  }
}
```

This means:
- KWW's direct Telegram conversations → Opus 4.6 (max quality)
- Loop's heartbeats → Nemotron local ($0/token)
- If Nemotron fails → falls back to Opus

### Interim (before Nemotron)

Until Nemotron is downloaded, use llama3.3:70b for heartbeats:

```json
{
  "heartbeat": {
    "model": "ollama/llama3.3:70b"
  }
}
```

Even without model switching, `lightContext: true` alone saves ~95% of
heartbeat token cost. Apply it NOW regardless of model status.

### After Applying

```bash
systemctl --user restart openclaw-gateway.service
# Verify gateway is up:
systemctl --user status openclaw-gateway.service
```

### Verification

Wait for the next heartbeat cycle. Check:
1. Does Loop respond? (even just structured heartbeat format)
2. Check gateway logs: `journalctl --user -u openclaw-gateway -n 20`
3. Verify model used in the log output
