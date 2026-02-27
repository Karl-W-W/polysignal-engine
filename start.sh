#!/bin/bash
set -x

# Add repository root to PYTHONPATH
# NOTE: /app/core is INTENTIONALLY EXCLUDED — it shadows stdlib `signal` module
# which causes circular import → Pydantic crash → Flask dies → container restart loop
export PYTHONPATH=$PYTHONPATH:/app

# Start Flask API (Core) in background — use -m invocation to avoid sys.path[0] = /app/core
echo "🚀 Starting Flask Core API (Port 5000)..."
python3 -m core.api > /app/flask.log 2>&1 &
FLASK_PID=$!

# Wait for Flask to initialize
sleep 5

# Start FastAPI Agent (Streaming) in background
echo "🚀 Starting FastAPI Agent Stream (Port 8000)..."
uvicorn agents.streaming:app --host 0.0.0.0 --port 8000 > /app/uvicorn.log 2>&1 &
FASTAPI_PID=$!

# Trap signals for cleanup
trap "kill $FLASK_PID $FASTAPI_PID 2>/dev/null; exit" SIGINT SIGTERM

# Option B: Independent restarts — if one process dies, restart it independently
# Don't use `wait -n` which kills the other on exit
while true; do
    # Check Flask
    if ! kill -0 $FLASK_PID 2>/dev/null; then
        echo "⚠️ Flask died. Restarting..."
        python3 -m core.api > /app/flask.log 2>&1 &
        FLASK_PID=$!
    fi
    # Check FastAPI (bounded crash — non-fatal)
    if ! kill -0 $FASTAPI_PID 2>/dev/null; then
        echo "⚠️ Uvicorn died. Restarting..."
        uvicorn agents.streaming:app --host 0.0.0.0 --port 8000 > /app/uvicorn.log 2>&1 &
        FASTAPI_PID=$!
    fi
    sleep 10
done
