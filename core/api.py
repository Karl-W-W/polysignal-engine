import threading
import json
import queue
from flask import Flask, jsonify, Response
from flask_cors import CORS
from workflows.masterloop import run_cycle as masterloop_run_cycle
import sqlite3
import os
from pathlib import Path

app = Flask(__name__)
CORS(app)

DB_PATH = os.getenv("DB_PATH", "/opt/loop/data/test.db")
DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/loop/data"))
LAB_DIR = Path(os.getenv("LAB_DIR", "/opt/loop/lab"))

# Global state for dashboard polling
LATEST_STATE = {
    "cycle_number": 0,
    "execution_status": "IDLE",
    "stage_timings": {},
    "logs": []
}

# SSE Broadcasting
SSE_QUEUES = []

def broadcast_event(type_, data):
    """Push an event to all connected SSE clients."""
    sse_msg = f"event: {type_}\ndata: {json.dumps(data)}\n\n"
    dead_queues = []
    for q in SSE_QUEUES:
        try:
            q.put_nowait(sse_msg)
        except queue.Full:
            dead_queues.append(q)
    for dq in dead_queues:
        if dq in SSE_QUEUES:
            SSE_QUEUES.remove(dq)


def _read_json(path: Path, default=None):
    """Read a JSON file, return default on any error."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


# ── Health ───────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({'status': 'operational', 'brain': 'LangGraph MasterLoop'})


# ── Scanner Status (live JSON) ───────────────────────────────────────────────

@app.route('/api/scanner/status')
def scanner_status():
    """Current scanner cycle, observations, predictions, errors."""
    data = _read_json(LAB_DIR / ".scanner-status.json", {})
    return jsonify(data)


# ── Prediction Accuracy (live JSON) ──────────────────────────────────────────

@app.route('/api/predictions/accuracy')
def prediction_accuracy():
    """Outcome evaluation stats + per-market tracking."""
    data = _read_json(DATA_DIR / "prediction_outcomes.json", {})
    stats = data.get("stats", {})
    per_market = data.get("per_market", {})
    predictions = data.get("predictions", [])
    unevaluated = len([p for p in predictions if not p.get("evaluated")])
    return jsonify({
        "stats": stats,
        "per_market_count": len(per_market),
        "records_in_file": len(predictions),
        "unevaluated": unevaluated,
    })


# ── Paper Trade P&L (live JSON) ──────────────────────────────────────────────

@app.route('/api/trades/summary')
def trades_summary():
    """Paper trade summary: count, W/L, P&L."""
    data = _read_json(LAB_DIR / "trading_log.json", {})
    trades = data.get("trades", [])
    evaluated = [t for t in trades if t.get("pnl") is not None]
    wins = len([t for t in evaluated if t.get("result") == "win"])
    losses = len([t for t in evaluated if t.get("result") == "loss"])
    total_pnl = sum(t["pnl"] for t in evaluated) if evaluated else 0.0
    return jsonify({
        "total_trades": len(trades),
        "evaluated": len(evaluated),
        "pending": len(trades) - len(evaluated),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / max(1, len(evaluated)), 3),
        "total_pnl": round(total_pnl, 2),
    })


# ── Latest Predictions (live JSON) ───────────────────────────────────────────

@app.route('/api/predictions/latest')
def latest_predictions():
    """Last 20 predictions from outcome tracker."""
    data = _read_json(DATA_DIR / "prediction_outcomes.json", {})
    predictions = data.get("predictions", [])
    latest = predictions[-20:] if predictions else []
    return jsonify(latest)


# ── System Overview (dashboard landing) ──────────────────────────────────────

@app.route('/api/system/stats')
def stats():
    """Combined system overview for dashboard."""
    scanner = _read_json(LAB_DIR / ".scanner-status.json", {})
    outcomes = _read_json(DATA_DIR / "prediction_outcomes.json", {})
    outcome_stats = outcomes.get("stats", {})
    return jsonify({
        "status": "SCANNER_ACTIVE" if scanner.get("cycle", 0) > 0 else "INITIALIZING",
        "scanner_cycle": scanner.get("cycle", 0),
        "markets_scanned": scanner.get("observations", 0),
        "predictions_per_cycle": scanner.get("predictions", 0),
        "errors": scanner.get("errors", 0),
        "accuracy": outcome_stats.get("accuracy", 0.0),
        "total_evaluated": outcome_stats.get("total_evaluated", 0),
        "total_predictions": outcome_stats.get("total_predictions", 0),
    })


# ── Legacy: narrative endpoint (returns latest predictions in old format) ────

@app.route('/api/narrative/latest')
def latest_narrative():
    """Latest predictions formatted for the signal cards on the dashboard."""
    data = _read_json(DATA_DIR / "prediction_outcomes.json", {})
    predictions = data.get("predictions", [])
    latest = predictions[-10:] if predictions else []
    signals = []
    for p in reversed(latest):
        signals.append({
            "title": f"{p.get('market_id', '?')} — {p.get('hypothesis', '?')}",
            "confidence": p.get("confidence", 0.0),
            "rationale": f"Cycle {p.get('cycle_number', '?')}, "
                         f"price {p.get('price_at_prediction', 0):.3f}, "
                         f"horizon {p.get('time_horizon', '?')}",
            "timestamp": p.get("timestamp", ""),
        })
    return jsonify(signals)


# ── SSE Stream ───────────────────────────────────────────────────────────────

@app.route('/api/stream')
def stream():
    def event_stream():
        q = queue.Queue(maxsize=100)
        SSE_QUEUES.append(q)
        try:
            initial_data = json.dumps(LATEST_STATE)
            yield f"event: INITIAL_STATE\ndata: {initial_data}\n\n"
            while True:
                msg = q.get()
                yield msg
        except GeneratorExit:
            SSE_QUEUES.remove(q)
    return Response(event_stream(), mimetype="text/event-stream")


# ── Run Cycle (fixed: was referencing undefined masterloop_orchestrator) ─────

@app.route('/api/run', methods=['POST'])
def run_cycle():
    from flask import request
    data = request.json or {}
    user_request = data.get('instruction', 'Autonomous System Check')

    def task():
        global LATEST_STATE
        print(f"Triggering Cycle: {user_request}")
        LATEST_STATE["execution_status"] = "RUNNING"
        broadcast_event("STATUS_UPDATE", {"status": "RUNNING"})
        try:
            final_state = masterloop_run_cycle(
                user_request,
                thread_id="dashboard_run",
                on_event=broadcast_event
            )
            LATEST_STATE.update(final_state)
            LATEST_STATE["execution_status"] = "IDLE"
            broadcast_event("STATUS_UPDATE", {"status": "IDLE"})
            broadcast_event("FINAL_STATE", final_state)
        except Exception as e:
            print(f"Cycle Failed: {e}")
            LATEST_STATE["execution_status"] = "ERROR"
            LATEST_STATE["error"] = str(e)
            broadcast_event("ERROR", {"message": str(e)})

    threading.Thread(target=task).start()
    return jsonify({"status": "Cycle Started", "instruction": user_request})


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(LATEST_STATE)


if __name__ == '__main__':
    print("API READY. Listening on 5000...")
    app.run(host='0.0.0.0', port=5000, threaded=True)
