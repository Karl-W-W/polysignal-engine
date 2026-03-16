# OpenClaw Gateway Security Architecture
# Source: KWW research (Session 26, 2026-03-16)
# For Loop: Read this, extract actionable items to LEARNINGS_TO_TASKS.md

## Key Findings

### Gateway vs Sandbox: There IS a Middle Ground

OpenClaw's security has 5 independently configurable layers:
1. **Network bind + authentication** (loopback + token)
2. **DM/channel access policies** (pairing/allowlist)
3. **Per-agent tool allow/deny lists**
4. **Docker container isolation** (seccomp + capability drops)
5. **Exec command allowlisting** with human-in-the-loop approval

### Minimal Deploy Permissions

For an agent that deploys code, the minimal viable permission set:
```json
{
  "agents": {
    "list": [{
      "id": "deployer",
      "sandbox": {
        "mode": "all",
        "scope": "agent",
        "workspaceAccess": "rw",
        "docker": { "network": "bridge" }
      },
      "tools": {
        "allow": ["read", "write", "edit", "apply_patch", "exec"],
        "deny": ["browser", "canvas", "nodes", "cron", "gateway", "sessions_spawn", "sessions_send"]
      }
    }]
  }
}
```

Critical: **deny `gateway`, `cron`, `sessions_spawn`, `sessions_send`** for deploy agents.
- `gateway` can modify config
- `cron` creates persistent scheduled actions
- `sessions_spawn`/`sessions_send` enable lateral movement

### Exec Allowlisting (Our Best Option)

Instead of `exec.security: "full"`, use `"allowlist"` mode:
```json
{
  "exec": {
    "security": "allowlist",
    "allowCommands": ["git *", "python3 -m pytest *", "systemctl --user restart *"],
    "ask": "on-miss",
    "askFallback": "deny"
  }
}
```
- `on-miss`: prompts for non-allowlisted commands
- `askFallback: "deny"`: unanswered prompts default to rejection

### Egress Proxy = Best Single Control

The `openclaw-vault` approach: mitmproxy sidecar that:
1. Injects API keys at the network layer (secrets never enter container)
2. Enforces domain allowlists
3. Prevents data exfiltration even if all other layers fail

**We already have this** — Squid proxy with 6-domain allowlist. This is our strongest defense.

### Known Vulnerabilities (Prioritize These)

- **CVE-2026-25253**: Unauthenticated RCE via token exfiltration (CVSS 8.8)
- **ClawJacked**: Cross-origin WebSocket hijacking of localhost agents
- **ClawHavoc**: 800+ malicious skills on ClawHub (Atomic macOS Stealer)
- **30,000+ instances** internet-exposed without auth
- Microsoft Security recommends full VM isolation, no shared credentials

### Our Security Architecture Assessment

| Layer | Our Status | Gap |
|-------|-----------|-----|
| Network bind | Loopback (good) | None |
| Auth | Token-based | Good |
| Tool deny | Missing `cron`, `sessions_*` denials | **Fix** |
| Container | Sandbox with bind mounts | Good |
| Seccomp | Not configured | **Add** |
| Read-only root | Not set | **Add** |
| Exec allowlist | `ask: off`, safeBins only | **Should use allowlist mode** |
| Egress | Squid proxy (6 domains) | Good |
| Secrets | root:root chmod 600 | Good |

### Actionable Recommendations for Our Setup

1. **Add `sessions_spawn` and `sessions_send` to deny list** — prevents Loop from spawning sub-agents or lateral movement
2. **Switch exec from safeBins to allowlist mode** — more granular than binary allow/deny
3. **Add seccomp profile** — block io_uring, ptrace, unshare, bpf syscalls
4. **Set `readOnlyRoot: true`** — prevent filesystem modification outside bind mounts
5. **Run `openclaw security audit --deep`** — automated misconfiguration detection
6. **Per-agent filesystem path ACLs** — currently a gap in OpenClaw (GitHub issue #12202)

### The Sandbox-Gateway Spectrum

```
FULL SANDBOX ←──── Our position ────→ FULL GATEWAY
(Docker, no host)                     (host exec, all access)

Our position: Sandbox + trigger files + deploy handler
Best position: Sandbox + exec allowlist + egress proxy
```

Our trigger-file approach (`.restart-scanner`, `.git-push-request`, `.deploy-trigger`) is actually a GOOD security pattern — it provides specific escape hatches to the host without granting broad access.
