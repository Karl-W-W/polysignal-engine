# Seven-Seat Layout — PolySignal-OS Operator Console

> Six Ghostty terminals on the DGX + one on the Mac for chat with Claude.
> Drafted during Session 41 clock-in (2026-04-24).
>
> Each seat answers one plain-language question. The idea is that you glance
> across six windows and know at once whether the system is healthy, what
> Loop is doing with your money, and whether the memory that compounds over
> time is actually being written down.

---

## Mac window — Claude the Architect (you ↔ me)

Your chat window with me (or whatever architect model is active).
Use this for: Vault-level decisions, strategy, clock-ins, anything that
isn't a mechanical task. This is where you pay for intelligence.

---

## DGX Seat 1 — Today's Fire

> **Plain question:** What's broken right now, and is the fix working?

- **Watches / drives:** whatever is on fire this session. Today: the two failing e2e tests + the `0xfake_*` trade pollution. Next week: whatever is breaking next week.
- **Why its own window:** a fire needs a rapid edit–test–verify loop without scrolling past unrelated noise from the other five windows. Separation keeps the test output visible while you're editing the test.
- **Opens on startup:**
  ```
  cd /opt/loop
  $EDITOR tests/test_masterloop_e2e.py    # in one pane
  # in another pane:
  watch -n 5 'grep -c 0xfake lab/trading_log.json 2>/dev/null || echo "log clean"'
  ```
- **Working vs dead:** you see file changes or pytest output in the last 5 minutes → alive. Same pytest failure line on screen for 20 min with no edits → dead, step back or ask for help.

---

## DGX Seat 2 — The Scanner (live data pulse)

> **Plain question:** Is the scanner actually running?

- **Watches / drives:** the scanner service heartbeat. Shows cycle count, predictions/cycle, errors, closest-signal delta. This is the one process that must run 24/7 — if it dies silently, every other number in the system is lies.
- **Why its own window:** dedicated visibility = you notice a scanner failure within one cycle (5 min) instead of within one heartbeat (2 h).
- **Opens on startup:**
  ```
  journalctl --user -u polysignal-scanner.service -f --since "10 min ago"
  # beside it:
  watch -n 30 'python3 -m json.tool lab/.scanner-status.json'
  ```
- **Working vs dead:** cycle number incremented in the last 5 minutes → alive. Same cycle number for 10+ minutes → scanner has crashed or stalled, investigate.

---

## DGX Seat 3 — The Truth Board (accuracy + trades)

> **Plain question:** Are we actually making money?

- **Watches / drives:** the only two numbers that matter for "are we profitable": recent directional accuracy and paper-trade P&L, computed honestly from source files. Independent of Loop's heartbeat summary (which has been stale).
- **Why its own window:** Loop currently reports accuracy pulled from `MEMORY.md` cache — that drifts. This seat gives you ground truth you can trust at a glance without opening a file.
- **Opens on startup:**
  ```
  cd /opt/loop
  watch -n 60 '.venv/bin/python3 -c "
import json, datetime as dt
d = json.loads(open(\"data/prediction_outcomes.json\").read())
preds = d[\"predictions\"]
now = dt.datetime.now(dt.timezone.utc)
def win(days):
    c = now - dt.timedelta(days=days)
    w = [p for p in preds if (t:=p.get(\"timestamp\")) and dt.datetime.fromisoformat(t.replace(\"Z\",\"+00:00\")) >= c]
    dr = [p for p in w if p.get(\"hypothesis\") in (\"Bullish\",\"Bearish\") and p.get(\"outcome\") in (\"CORRECT\",\"INCORRECT\")]
    co = [p for p in dr if p.get(\"outcome\")==\"CORRECT\"]
    return len(dr), len(co)
for d_ in [1,3,7,14,30]:
    n,c = win(d_)
    print(f\"{d_}d: {c}/{n} = {100*c/n:.1f}%\" if n else f\"{d_}d: no directional evals\")
tl = json.loads(open(\"lab/trading_log.json\").read())[\"trades\"]
real = [t for t in tl if not str(t.get(\"market_id\",\"\")).startswith(\"0xfake\")]
last100 = real[-100:]
res = [t for t in last100 if (t.get(\"result\") or (t.get(\"evaluation\") or {}).get(\"outcome\")) not in (None,\"pending\",\"\")]
w = [t for t in res if (t.get(\"result\") or (t.get(\"evaluation\") or {}).get(\"outcome\"))==\"win\"]
print(f\"real trades last-100: {len(w)}/{len(res)} win = {100*len(w)/len(res):.1f}%\" if res else \"no resolved\")
"'
  ```
  (or `lab/truth_board.py` as a clean one-shot — drop-in easy, ~30 lines.)
- **Working vs dead:** numbers refresh each minute → alive. Same numbers for an hour → scanner isn't producing new evaluated predictions, or truth-board script has errored. Check the other seats.

---

## DGX Seat 4 — Compounding Brain (the moat)

> **Plain question:** What did I just learn, and is it written down?

- **Watches / drives:** `brain/memory.md` and `lab/LEARNINGS_TO_TASKS.md`. The seat's only purpose is to force you to pause and curate — nothing learned this session escapes to future-you without being captured here.
- **Why its own window:** if memory capture shares a window with work-in-progress, it always loses to the shinier thing. A dedicated seat whose only job is "write it down" is the whole point of running a system that's supposed to get smarter over time. Intentionally manual — no automation should own this.
- **Opens on startup:**
  ```
  cd /opt/loop
  $EDITOR brain/memory.md lab/LEARNINGS_TO_TASKS.md    # split panes
  # beside it, for context on what's happened since last session:
  git log --since "yesterday" --stat --pretty='format:%h %s'
  ```
- **Working vs dead:** `brain/memory.md` got at least one new line per session → alive. Untouched for 3+ sessions → dead, and the system is regressing silently. Hard rule: **don't close the Mac-Claude window at end of session until this seat has one new entry.**

---

## DGX Seat 5 — Loop (the agent)

> **Plain question:** What is Loop doing with my money?

- **Watches / drives:** Loop's cost, token burn, and heartbeat text. Also where you send Loop direct messages via the `openclaw agent` CLI when you want a second opinion (the S40 Orbán-verification pattern).
- **Why its own window:** Loop's cost and behavior are the one thing nobody looks at between sessions — which is how the S40 $50 surprise happened. Dedicated seat puts cost in your peripheral vision and keeps the direct-message incantation one copy-paste away.
- **Opens on startup:**
  ```
  cd /opt/loop
  watch -n 60 '.venv/bin/python3 -c "
import json
d = json.loads(open(\"/home/cube/.openclaw/agents/main/sessions/sessions.json\").read())[\"agent:main:main\"]
print(f\"model={d[\"model\"]}  status={d[\"status\"]}\")
print(f\"cost=\\${d.get(\"estimatedCostUsd\",0):.3f}  tokens={d.get(\"totalTokens\",0)}\")
print(f\"last-heartbeat={d.get(\"lastHeartbeatSentAt\",\"-\")}\")
print(f\"text: {(d.get(\"lastHeartbeatText\") or \"\")[:200]}\")
"'
  # scratch pane, ready to DM Loop:
  # openclaw agent --channel telegram --to 1822532651 --deliver --message "..."
  ```
- **Working vs dead:** `last-heartbeat` advances every ~2 hours → alive. Cost jumps >$1 in a single heartbeat → dead, investigate immediately (stuck session or failover loop). No new heartbeat in 4+ hours → Loop is asleep or the gateway is down.

---

## DGX Seat 6 — System Vitals (the body)

> **Plain question:** Is the machine healthy?

- **Watches / drives:** GPU thermals, disk space, memory, and systemd status for the five critical services (scanner, openclaw-gateway, cloudflared, squid, polysignal-scanner-restart path unit). One glance = "is the hardware OK."
- **Why its own window:** when a node dies, the symptoms show up in other seats as "cycle frozen" or "cost spike." Dedicated vitals seat turns that into an early warning — you see thermals climbing before the scanner falls over.
- **Opens on startup:**
  ```
  watch -n 10 'nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv,noheader; \
    echo ---; df -h / /opt/loop | tail -2; \
    echo ---; systemctl --user is-active polysignal-scanner.service openclaw-gateway.service'
  # scratch pane for restarts:
  # systemctl --user restart polysignal-scanner.service
  ```
- **Working vs dead:** temps in 50–75 °C range and all services `active` → alive. Temp > 85 °C or any service `failed`/`inactive` → flashing red, fix this before touching anything else.

---

## Why the split holds together

- **Fire (1) and Scanner (2) are the feedback loops** for what's broken *now* vs what must *never* break. Fire is short-timescale; Scanner is continuous-timescale.
- **Truth Board (3)** exists because Loop currently misreports the numbers. Until that's fixed, ground truth deserves its own seat.
- **Compounding Brain (4)** is the whole point of the system. Drop it and everything else is a treadmill.
- **Loop (5) and Vitals (6)** are the two monitor-only seats — one for the agent, one for the machine. They should be the quietest; that's what you want for monitors.
- **Mac-Claude** is where the decisions happen. The DGX seats execute; the Mac thinks.

## One-liner cheat sheet

| Seat | Plain question |
|------|----------------|
| Mac-Claude | What's the right next move? |
| 1. Fire | What's broken right now, and is the fix working? |
| 2. Scanner | Is the scanner actually running? |
| 3. Truth Board | Are we actually making money? |
| 4. Brain | What did I just learn, and is it written down? |
| 5. Loop | What is Loop doing with my money? |
| 6. Vitals | Is the machine healthy? |
