# Session Prompts

Canonical session prompts for PolySignal-OS. Copy-paste these into Claude Code / Antigravity to start a session.

---

## CLOCK-IN

Clocking in to PolySignal-OS. Follow this sequence:

### Phase 1: Load Context (read silently, don't respond yet)
0. Read CLAUDE.md — your operating manual
1. Read ARCHITECTURE.md Section 1 — epistemology
2. Read lab/NOW.md — Loop's operational state
3. Read lab/LOOP_TASKS.md — task queue
4. Read lab/GOALS.md — master goal list
5. Read PROGRESS.md — last 2 sessions only

### Phase 2: Detect Changes
6. `git log --oneline --since="24 hours ago"`
7. `git diff HEAD~3 --stat`
8. `find lab/ -newer lab/NOW.md -name "*.py" -o -name "*.md"`
9. `ls -la lab/.retrain-trigger lab/.git-push-request lab/.restart-scanner 2>/dev/null`

### Phase 3: Verify Health
10. `python3 -m pytest tests/ --tb=short -k 'not test_api' -q`
11. SSH to DGX: `cd ~/polysignal-os && cat lab/.scanner-status.json`
12. SSH to DGX: `cd ~/polysignal-os && python3 -c "
    import json
    with open('lab/trading_log.json') as f:
        trades = json.load(f)
    resolved = [t for t in trades if t.get('result') != 'pending']
    pending = [t for t in trades if t.get('result') == 'pending']
    print(f'Trades: {len(trades)} total, {len(resolved)} resolved, {len(pending)} pending')
    if resolved:
        wins = [t for t in resolved if t.get('result') == 'win']
        print(f'P&L: {len(wins)}W / {len(resolved)-len(wins)}L')
    "`
13. SSH to DGX: `cd ~/polysignal-os && curl -s http://localhost:18789/__openclaw__/api/health | head -5`

### Phase 4: Think Before Reporting
Before responding, consider:
- Is accuracy improving or declining since last session?
- Are paper trades evaluating (resolved count growing)?
- Is Loop using Claude Sonnet or falling back to llama3.3?
- Does GOALS.md Tier 1 match what Loop is actually doing?
- Any contradictions between GOALS.md and LOOP_TASKS.md?
- Did Loop's overnight work duplicate existing code?

### Phase 5: Report
1) What Loop accomplished overnight (files, tasks)
2) Scanner: cycle count, predictions/cycle, errors
3) Trading: total trades, resolved vs pending, win rate
4) Accuracy: overall + per-category if available
5) Loop status: model in use, last heartbeat, exec working?
6) Tests: count + any failures
7) Concerns: what's broken or degrading
8) Recommended focus with model suggestion
