# OpenClaw DGX Spark Configuration Spec (v2)

**Author:** Antigravity, Shift 3 | **Date:** 2026-02-24  
**Status:** SUPERSEDED by `model_upgrade.md` (2026-02-25). Model is now Claude Opus 4.6 via Anthropic API, not local Ollama. Heartbeat and security sections remain valid reference material.

---

## Architecture (Corrected — DGX-Local)

```
You (phone) → Telegram message
    → OpenClaw daemon (DGX Spark, systemd service)
    → localhost:11434 Ollama (llama3.3:70b)
    → DGX reasons, generates tool calls
    → OpenClaw executes locally on DGX (filesystem, shell)
    → Response back to Telegram
```

OpenClaw already runs **on the DGX** as a systemd service (`openclaw-gateway.service`). Ollama is at `localhost:11434`. No LAN hop. No Mac relay. Everything is local.

---

## Current State (Before Changes)

| Setting | Current | Target |
|---|---|---|
| **Primary model** | `qwen2.5:14b` | `llama3.3:70b` |
| **Fallback** | `llama3.3:70b` | `deepseek-r1:70b` (keep) |
| **Heartbeat** | Not configured (SILENT MODE) | Every 30m, 5-task watchdog |
| **MoltBook skill** | ~~Installed~~ → ✅ **REMOVED** | Permanently excluded |
| **Sandbox** | `mode: "all"` | Keep |
| **Telegram conflict** | ⚠️ 409 every 30s (two bots) | Stop `loop-telegram` |
| **Exec security** | Default | `allowlist` + `ask: "on-miss"` |

---

## 1. `openclaw.json` Patch (Apply on Top of Existing Config)

Only the changed/added fields — the existing `gateway`, `plugins`, `channels`, `commands`, `messages`, `skills` blocks remain untouched.

```json5
{
  // ── Model: Promote llama3.3:70b to primary ───────────
  agents: {
    defaults: {
      model: {
        primary: "ollama/llama3.3:70b",               // was: qwen2.5:14b
        fallbacks: ["ollama/deepseek-r1:70b"],         // was: llama3.3:70b
      },

      // ── Heartbeat: 30-minute watchdog ─────────────
      heartbeat: {
        every: "30m",
        target: "telegram",
        activeHours: { start: "07:00", end: "01:00" },
        ackMaxChars: 300,
        suppressToolErrorWarnings: false,
      },

      // ── Timezone ──────────────────────────────────
      userTimezone: "Europe/Berlin",
    },
  },

  // ── Tool Policy (SECURITY-CRITICAL) ───────────────────
  tools: {
    profile: "coding",
    deny: ["browser", "canvas"],

    exec: {
      host: "sandbox",                                 // Maintain sandbox mode
      security: "allowlist",                           // Every new command type needs approval
      ask: "on-miss",                                  // Prompt for approval on unknown commands
      timeoutSec: 300,
      notifyOnExit: true,

      safeBins: ["cat", "head", "tail", "wc", "grep", "find", "ls", "date", "echo", "curl", "df"],

      applyPatch: {
        enabled: false,                                // No model-generated file edits
        workspaceOnly: true,
      },
    },

    elevated: {
      enabled: false,                                  // No sandbox bypass
    },
  },
}
```

### How to Apply

```bash
# Use OpenClaw CLI to patch specific fields:
openclaw config set agents.defaults.model.primary "ollama/llama3.3:70b"
openclaw config set agents.defaults.model.fallbacks '["ollama/deepseek-r1:70b"]'
openclaw config set agents.defaults.heartbeat.every "30m"
openclaw config set agents.defaults.heartbeat.target "telegram"
openclaw config set agents.defaults.heartbeat.activeHours '{"start":"07:00","end":"01:00"}'
openclaw config set agents.defaults.heartbeat.ackMaxChars 300
openclaw config set agents.defaults.userTimezone "Europe/Berlin"
openclaw config set tools.profile "coding"
openclaw config set tools.deny '["browser","canvas"]'
openclaw config set tools.exec.security "allowlist"
openclaw config set tools.exec.ask "on-miss"
openclaw config set tools.exec.timeoutSec 300
openclaw config set tools.exec.safeBins '["cat","head","tail","wc","grep","find","ls","date","echo","curl","df"]'
openclaw config set tools.elevated.enabled false
```

---

## 2. `HEARTBEAT.md` (Deploy to `~/.openclaw/workspace/HEARTBEAT.md`)

Replaces the current "SILENT MODE" placeholder.

```markdown
# PolySignal-OS Watchdog — Heartbeat Checklist

Execute each item in order. If nothing needs attention, reply HEARTBEAT_OK.
Only alert on actionable findings — do not echo "all good" for each item.

## 1. Flask API Health
- `curl -s --max-time 5 http://localhost:5000/api/status`
- Report `cycle_number` and `execution_status` from the JSON response.
- If request fails or times out: alert "Flask API unreachable."

## 2. Signal Scan Log
- `tail -20 /opt/loop/data/logs/signal_scan.log 2>/dev/null || tail -20 /opt/loop/lab/experiments/signal_scan.log 2>/dev/null`
- Count lines containing "SIGNAL:" — report the count and the last SIGNAL entry.
- If the log hasn't been modified in >2 hours: alert "Signal scan may be stalled."

## 3. Market Observation Count
- `python3 -c "import sqlite3; db=sqlite3.connect('/opt/loop/polysignal.db'); c=db.execute(\"SELECT COUNT(*) FROM observations WHERE timestamp > datetime('now', '-1 hour')\"); print(f'Observations last hour: {c.fetchone()[0]}')" 2>/dev/null`
- Report the count. If zero: alert "No observations recorded in the last hour."

## 4. Container Health
- `docker ps --format '{{.Names}}: {{.Status}}' | grep loop`
- Report any containers not in "Up" state.

## 5. Disk Space
- `df -h /opt/loop | tail -1 | awk '{print "Disk: " $5 " used"}'`
- Alert only if usage exceeds 85%.
```

> [!IMPORTANT]
> All commands run **locally on the DGX** — no SSH needed. OpenClaw is on the same machine as Ollama, Flask, Docker, and the signal DB.

---

## 3. Security Boundaries

| Boundary | Setting | Effect |
|---|---|---|
| Exec approval | `security: "allowlist"` + `ask: "on-miss"` | Every new command type needs Telegram "YES" |
| Safe bins | `cat`, `head`, `tail`, `grep`, `ls`, `curl`, `df`, etc. | Read-only commands run without approval |
| Sandbox | `mode: "all"` | All exec runs sandboxed |
| Elevated exec | `enabled: false` | No sandbox bypass possible |
| Browser | `deny: ["browser", "canvas"]` | No web browsing |
| Workspace writes | `applyPatch.workspaceOnly: true` | File writes confined to workspace |
| MoltBook | **DELETED** 2026-02-24 | Skill files + SOUL.md reference removed |

### Constraints from `telegram_lockdown.md` → Translated to OpenClaw

| Docker lockdown | OpenClaw equivalent | Status |
|---|---|---|
| Drop root user | OpenClaw runs as `cube` (uid 1000) | ✅ Already in place |
| Scope env keys (only TELEGRAM_*) | OpenClaw reads its own config, not `/opt/loop/.env` | ✅ Already isolated |
| `read_only: true` filesystem | `sandbox.mode: "all"` + `applyPatch.workspaceOnly: true` | ✅ In spec |
| `cap_drop: ALL` | `tools.exec.security: "allowlist"` | ✅ In spec |
| No NVIDIA/HMAC/LANGCHAIN keys | Keys are in `/opt/loop/.env`, not in `~/.openclaw/` | ✅ Already isolated |
| `/data:ro` mount | OpenClaw can read `/opt/loop/` but writes go to sandbox | ✅ Sandbox enforced |

---

## 4. Phase 3 — Cutover Checklist (Requires Authorization)

```bash
# 1. Stop loop-telegram (resolves 409 conflict)
cd /opt/loop && docker compose stop telegram

# 2. Apply config changes
openclaw config set agents.defaults.model.primary "ollama/llama3.3:70b"
openclaw config set agents.defaults.model.fallbacks '["ollama/deepseek-r1:70b"]'
openclaw config set agents.defaults.heartbeat.every "30m"
openclaw config set agents.defaults.heartbeat.target "telegram"
openclaw config set agents.defaults.heartbeat.activeHours '{"start":"07:00","end":"01:00"}'
openclaw config set agents.defaults.heartbeat.ackMaxChars 300
openclaw config set agents.defaults.userTimezone "Europe/Berlin"
openclaw config set tools.profile "coding"
openclaw config set tools.deny '["browser","canvas"]'
openclaw config set tools.exec.security "allowlist"
openclaw config set tools.exec.ask "on-miss"
openclaw config set tools.exec.timeoutSec 300
openclaw config set tools.exec.safeBins '["cat","head","tail","wc","grep","find","ls","date","echo","curl","df"]'
openclaw config set tools.elevated.enabled false

# 3. Deploy HEARTBEAT.md watchdog
cat > ~/.openclaw/workspace/HEARTBEAT.md << 'HEARTBEAT_EOF'
# PolySignal-OS Watchdog — Heartbeat Checklist

Execute each item in order. If nothing needs attention, reply HEARTBEAT_OK.
Only alert on actionable findings — do not echo "all good" for each item.

## 1. Flask API Health
- `curl -s --max-time 5 http://localhost:5000/api/status`
- Report `cycle_number` and `execution_status` from the JSON response.
- If request fails or times out: alert "Flask API unreachable."

## 2. Signal Scan Log
- `tail -20 /opt/loop/data/logs/signal_scan.log 2>/dev/null || tail -20 /opt/loop/lab/experiments/signal_scan.log 2>/dev/null`
- Count lines containing "SIGNAL:" — report the count and the last SIGNAL entry.
- If the log hasn't been modified in >2 hours: alert "Signal scan may be stalled."

## 3. Market Observation Count
- `python3 -c "import sqlite3; db=sqlite3.connect('/opt/loop/polysignal.db'); c=db.execute(\"SELECT COUNT(*) FROM observations WHERE timestamp > datetime('now', '-1 hour')\"); print(f'Observations last hour: {c.fetchone()[0]}')" 2>/dev/null`
- Report the count. If zero: alert "No observations recorded in the last hour."

## 4. Container Health
- `docker ps --format '{{.Names}}: {{.Status}}' | grep loop`
- Report any containers not in "Up" state.

## 5. Disk Space
- `df -h /opt/loop | tail -1 | awk '{print "Disk: " $5 " used"}'`
- Alert only if usage exceeds 85%.
HEARTBEAT_EOF

# 4. Clear stale sessions (removes cached MoltBook skill references)
rm -f ~/.openclaw/agents/main/sessions/sessions.json

# 5. Restart OpenClaw
systemctl --user restart openclaw-gateway

# 6. Verify startup
sleep 5
systemctl --user status openclaw-gateway | head -10
journalctl --user -u openclaw-gateway --since "1 min ago" | tail -20

# 7. Test from Telegram
# Send: "status" → expect llama3.3:70b-powered response with real system data
# Send: "What model are you using?" → expect "ollama/llama3.3:70b" or "Llama 3.3 70B"
```

---

## 5. Rollback Plan

If anything goes wrong after Phase 3:

```bash
# Restart loop-telegram (reverts to old dual-bot conflict)
cd /opt/loop && docker compose start telegram

# Restore OpenClaw config from backup
cp ~/.openclaw/openclaw.json.bak ~/.openclaw/openclaw.json
systemctl --user restart openclaw-gateway
```

---

## 6. What This Achieves

After Phase 3, you text "status" from your phone. Within 10 seconds:

- OpenClaw reads your Telegram message
- DGX Spark (128GB unified memory, `llama3.3:70b`) reasons about your request
- Reads the signal log, pings Flask, checks containers
- Reports back: "Cycle #47, IDLE. 23 observations last hour. 3 signals detected. All containers up. Disk: 34% used."

Every 30 minutes, unprompted — the same report arrives on your phone if anything needs attention. If everything is fine: silence. You walk down the street. Your DGX watches the markets.
