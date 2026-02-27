# lab/start_sh_fix.md
# DGX start.sh Bug — Fix Proposal for Human Review

## Bug Description

**Container**: `loop-backend-1`
**Symptom**: Backend crashes on startup with:
```
ModuleNotFoundError: No module named 'flask'
```
then immediately exits, killing the other process via `wait -n`.

## Root Cause

`start.sh` runs `python3 core/api.py` directly as a subprocess.
Inside Docker, flask IS installed → this works.
The crash we observed was `agents.streaming` (FastAPI) failing to start,
which caused `wait -n` to exit immediately, killing Flask too.
Both processes share a single process group — one death kills both.

## What Actually Crashes (the real culprit)

```bash
uvicorn agents.streaming:app  # this fails silently
```

Likely cause: `agents/streaming.py` imports something not available in the container
(previously `agents/telegram.py` was the shadow — now fixed, but streaming may have
its own import issue).

## Proposed Fix

**Option A (minimal):** Add error logging so we know which service died:
```bash
# start.sh change — log the failure before exiting
python3 core/api.py > /app/flask.log 2>&1 &
FLASK_PID=$!
uvicorn agents.streaming:app --host 0.0.0.0 --port 8000 > /app/uvicorn.log 2>&1 &
FASTAPI_PID=$!

wait -n $FLASK_PID $FASTAPI_PID
echo "⚠️ One service exited. Flask log:"
tail -20 /app/flask.log
echo "Uvicorn log:"
tail -20 /app/uvicorn.log
```

**Option B (resilient):** Restart each service independently on failure:
```bash
while true; do
    python3 core/api.py 2>&1 | tee /app/flask.log
    echo "Flask exited — restarting in 5s"
    sleep 5
done &

while true; do
    uvicorn agents.streaming:app --host 0.0.0.0 --port 8000 2>&1 | tee /app/uvicorn.log
    echo "Uvicorn exited — restarting in 5s"
    sleep 5
done &

wait
```

## Verification Steps

1. Apply fix to `/opt/loop/start.sh`
2. Rebuild: `docker compose build backend && docker compose up -d backend`
3. Check: `docker logs loop-backend-1 --tail 20`
4. Expected: Both Flask (port 5000) and Uvicorn (port 8000) running
5. Confirm: `curl http://localhost:5000/api/status` returns JSON

## Recommendation

**Use Option A first** — it's the smallest change. It will reveal what's actually
crashing (Flask or Uvicorn). Once we know which service dies, we can apply Option B
selectively only to the failing one.

## Authorization Required

Do NOT apply this to `/opt/loop/start.sh` on DGX without explicit human approval.
Current status: PROPOSED. Awaiting review.
