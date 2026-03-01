# PolySignal-OS — Current System State
# Last updated: 2026-03-01 18:30 CET | Session 8 closed
# Session history: See HISTORY.md

---

## System Overview

PolySignal-OS is an AI-native prediction market intelligence system. It scans Polymarket via the Gamma API, detects signals through a 6-stage MasterLoop (LangGraph), and surfaces ~5 high-confidence signals/week. Deployed on NVIDIA DGX Spark (Munich), frontend on Vercel.

**Pipeline (complete, risk-gated):**
```
Polymarket → PERCEPTION → PREDICTION → DRAFT → REVIEW → RISK_GATE → COMMIT → Telegram
```

**Three-agent workflow:**
- **Antigravity** (Claude Code / DGX access) — architect, infrastructure, test runner
- **Loop** (OpenClaw sandbox / Telegram) — autonomous developer, reads/writes code
- **Karl** — router, Vault authorizer, human-only tasks

---

## Infrastructure Status

| Component | Status | Details |
|-----------|--------|---------|
| DGX Spark | UP | Munich, `llama3.3:70b` on Ollama |
| Docker Backend | UP | Flask :5000, Uvicorn :8000, rebuilt with risk gate |
| OpenClaw Sandbox | UP | Firejail :9001, 10 bind mounts |
| OpenClaw Gateway | UP | systemd, Claude Opus 4.6, heartbeat 30m |
| Telegram Bot | UP | `@OpenClawOnDGX_bot`, allowlist: [1822532651] |
| Frontend | LIVE | `polysignal-os.vercel.app` (Vercel) |
| Cloudflare Tunnel | UP | DGX → polysignal.app |
| LangSmith | ENABLED | EU endpoint, `LANGCHAIN_TRACING_V2=true` |
| GitHub | SYNCED | `7427f6c`, Mac + DGX both current |
| Tests | 86/86 PASS | Mac (0.34s) + DGX (0.33s) |
| Risk Gate | WIRED | review → risk_gate → commit (kill switch OFF) |
| Loop Autonomy | BLOCKED | TASKS.md mounted, heartbeat firing, but Anthropic credits depleted |

## Vault Inventory (`/opt/loop/core/` — 9 files)

| File | Purpose |
|------|---------|
| `perceive.py` | Polymarket Gamma API scanner |
| `predict.py` | Pattern matching, momentum detection |
| `supervisor.py` | NVIDIA NIM + HMAC audit (fast/slow path) |
| `bridge.py` | OpenClaw LangChain tool wrapper |
| `api.py` | Flask REST API (status, stats, narrative, SSE) |
| `notifications.py` | Telegram alert dispatcher |
| `openclaw_api.py` | Firejail sandbox executor |
| `signal_model.py` | Canonical Signal schema (Pydantic V2) |
| `risk.py` | Risk gate ($10 max, 75% confidence, $50 daily cap, kill switch) |

## MasterLoop Graph (7 nodes)

```
perception → prediction → draft → review → risk_gate → [approved] → wait_approval → commit → END
                                              ↓
                                        [RISK_BLOCKED] → END
```

---

## Revenue Readiness

| Capability | Status | Blocker |
|-----------|--------|---------|
| Polymarket scanning | LIVE | — |
| Signal detection (typed) | LIVE | — |
| Risk gate | WIRED | Kill switch OFF (intentional) |
| HMAC audit | LIVE | — |
| Sandboxed execution | LIVE | — |
| Telegram alerts | LIVE | — |
| MoltBook broadcast | BLOCKED | Human: Twitter verification |
| Polymarket wallet | NOT STARTED | Needs `risk.py` + wallet setup |
| Custom domain | BLOCKED | Human: DNS CNAME + Vercel |
| Anthropic credits (Loop) | CHECK | Top up at console.anthropic.com |

**To go live (human-only steps):**
1. Top up Anthropic API credits (Loop is dead without them)
2. MoltBook registration: `moltbook.com/api/v1/register` → Twitter verify → JWT → `openclaw.json`
3. DNS: CNAME `polysignal.app` → `cname.vercel-dns.com` + Vercel dashboard
4. Polymarket wallet setup (after MoltBook is active)
5. `TRADING_ENABLED=true` (only after wallet exists)

---

## Open Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| Anthropic credits for Loop | HIGH | Loop can't work without API credits |
| MoltBook skill INACTIVE | MEDIUM | Built + sanitized. Needs Twitter verification (human-only). |
| No Polymarket wallet | MEDIUM | Can't execute trades. Needs wallet + CLOB auth. |
| `polysignal.app` DNS | LOW | CNAME → `cname.vercel-dns.com` + Vercel dashboard. |
| No Python in sandbox | LOW | Loop can write code but not test. Antigravity runs tests. |
| `group:memory` plugin warning | COSMETIC | OpenClaw v2026.2.12 built-in. Can't fix without upgrade. |

---

## Priorities

### P0: Anthropic Credits (HUMAN)
Top up at console.anthropic.com. Without credits, Loop is dead — heartbeat fires but API rejects.

### P1: MoltBook Registration (HUMAN)
The signal broadcaster is the product. Register, get JWT, add to OpenClaw sandbox env.

### P2: DNS (HUMAN)
`polysignal.app` → Vercel. Makes the product real.

### P3: Polymarket Wallet Setup
After MoltBook is active. Read-only CLOB client already works (14 markets probed in Session 2).

### P4: Loop Tasks (AUTONOMOUS)
TASKS.md has: TradeProposal.from_signal() bridge, cycle_number fix, MasterLoop e2e test.

---

## Hard Rules

- `core/` is the Vault — read-only without explicit human authorization
- `lab/` is the scratchpad — build here, test, request promotion
- `workflows/` is editable with justification (not Vault)
- Docker config changes need container **destruction**, not restart
- Never re-add `"api": "anthropic-messages"` to `openclaw.json`
- Never restart `loop-telegram` — OpenClaw owns Telegram
- No `TRADING_ENABLED=true` until Polymarket wallet exists
- No credentials in markdown files or chat history
