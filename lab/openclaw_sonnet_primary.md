# OpenClaw — swap agent `main` primary to Sonnet 4.6 (S43)

## Summary

Agent `main`'s primary model swapped from `claude-haiku-4-5-20251001` to
`claude-sonnet-4-6`. Haiku 4.5 moved into the fallback chain as a cost
guardrail. Heartbeat model is **not** changed — still on Haiku, separate
config key.

## What changed

Edited on DGX: `~/.openclaw/openclaw.json`
Affected JSON path: `.agents.defaults.model`

Before:

```json
{
  "primary": "anthropic/claude-haiku-4-5-20251001",
  "fallbacks": [
    "ollama/llama3.3:70b",
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-opus-4-6"
  ]
}
```

After:

```json
{
  "primary": "anthropic/claude-sonnet-4-6",
  "fallbacks": [
    "anthropic/claude-haiku-4-5-20251001",
    "ollama/llama3.3:70b",
    "anthropic/claude-opus-4-6"
  ]
}
```

Heartbeat model (`.agents.defaults.heartbeat.model`) intentionally left at
`anthropic/claude-haiku-4-5-20251001` — heartbeats are short ack replies
where Sonnet's reasoning gain doesn't justify 3× input + 3× output rates.
See "Cost impact" below for the math if a later session wants to swap it.

## Why

Two reasons:

1. **Eliminates IDENTITY drift.** `~/.openclaw/workspace/IDENTITY.md` line 5
   already declared `Model: anthropic/claude-sonnet-4-6 (primary)`. Runtime
   was on Haiku 4.5. The agent character thought it was Sonnet; it was
   actually Haiku. This swap brings runtime in line with the identity doc.

2. **Smarter operator chat in Seat 6.** During verification of
   `scripts/loop_chat.sh`, Haiku 4.5 read `Reply with exactly: the cube
   root of 729.` literally and replied with the string `"the cube root of
   729."` instead of computing 9. Sonnet handles instruction-following
   ambiguity better — important for the operator REPL where messages
   often blend directives with content.

## How (commands)

```sh
ssh dgx-remote
BAK=~/.openclaw/openclaw.json.bak-pre-sonnet-$(date +%Y%m%d-%H%M%S)
cp ~/.openclaw/openclaw.json "$BAK"
jq '.agents.defaults.model.primary = "anthropic/claude-sonnet-4-6" |
    .agents.defaults.model.fallbacks = [
      "anthropic/claude-haiku-4-5-20251001",
      "ollama/llama3.3:70b",
      "anthropic/claude-opus-4-6"
    ]' ~/.openclaw/openclaw.json > /tmp/openclaw.json.new
jq empty /tmp/openclaw.json.new    # validate
mv /tmp/openclaw.json.new ~/.openclaw/openclaw.json
systemctl --user restart openclaw-gateway.service
```

Gateway restart required: `systemctl show openclaw-gateway.service -p
ExecReload` is empty (no hot-reload), and the prior heartbeat-config spec
in `lab/openclaw_heartbeat_config.md` calls out the same restart step.

Backup file on DGX: `~/.openclaw/openclaw.json.bak-pre-sonnet-<timestamp>`
(specific timestamp captured at apply time).

## Verification

Run after restart:

```sh
openclaw agent --agent main --session-id swap-verify-$(date +%s) \
  --message "What is 7 times 8? Respond with just the number." \
  --json --timeout 60 | jq '..|.text? // empty' | grep -v null
```

Expected: `"56"`. Got: `"56"` (gateway ready in 1s after restart).

`openclaw agents` confirms `Model: anthropic/claude-sonnet-4-6` is now in
effect.

## Cost impact

Heartbeat math (output only; input tokens were not specified in the swap
brief, so this is a lower bound):

- Cadence: every 120 min, active window 07:00–01:00 → 9 firings/day
- Output cap: 300 chars ≈ 75 tokens per firing
- Haiku output: $5/MTok → 9 × 75 × $5/1M = **$0.0034/day**
- Sonnet output: $15/MTok → 9 × 75 × $15/1M = **$0.0101/day**
- **Delta (output only): +$0.0067/day ≈ +$0.20/month**

This is the output-only delta if the heartbeat were also swapped. Since
heartbeat is **not** swapped in this commit, real cost impact is $0/day
for the heartbeat path. For the operator chat path (Seat 6) the delta is
load-dependent — Sonnet input is 3× Haiku input, so heavy chat sessions
will see ~3× chat-related spend.

Full-context worst case (if heartbeat were on full 170K-token bootstrap,
which the current config doesn't claim — no `lightContext: true`): delta
rises to ~+$3/day. Keep this in mind if heartbeat is ever moved off Haiku
without first setting `lightContext: true`.

## Rollback

```sh
ssh dgx-remote
ls -t ~/.openclaw/openclaw.json.bak-pre-sonnet-* | head -1   # find latest
cp ~/.openclaw/openclaw.json.bak-pre-sonnet-<timestamp> ~/.openclaw/openclaw.json
systemctl --user restart openclaw-gateway.service
```

## Open items

- IDENTITY.md line 6 says `Fallback chain: ollama/llama3.3:70b (free) →
  anthropic/claude-opus-4-6 (last resort)` — does not mention Haiku 4.5
  as first fallback. Narrative, not strict spec, but worth tightening on
  the next IDENTITY pass.
- Heartbeat model swap is a separate decision; cost delta above
  estimates the lower bound.
