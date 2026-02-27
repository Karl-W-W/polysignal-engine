import threading
import time
import json
import queue
from flask import Flask, jsonify, Response, stream_with_context
from flask_cors import CORS
# import masterloop_orchestrator  # OLD
from workflows.masterloop import run_cycle as masterloop_run_cycle  # Fixed: orchestrator no longer exists
import sqlite3
import os

app = Flask(__name__)
CORS(app)

DB_PATH = "/data/polysignal.db"

# Global state for dashboard polling (Legacy support)
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
    event = {
        "event": type_,
        "data": json.dumps(data)
    }
    # Format as SSE string
    sse_msg = f"event: {type_}\ndata: {json.dumps(data)}\n\n"
    
    dead_queues = []
    for q in SSE_QUEUES:
        try:
            q.put_nowait(sse_msg)
        except queue.Full:
            dead_queues.append(q)
    
    # Remove full/dead queues
    for dq in dead_queues:
        if dq in SSE_QUEUES:
            SSE_QUEUES.remove(dq)

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/health')
def health():
    return jsonify({'status': 'operational', 'brain': 'LangGraph MasterLoop'})

@app.route('/api/system/stats')
def stats():
    print("DEBUG: Accessing /api/system/stats", flush=True)
    try:
        conn = get_db()
        # Get stats from new tables populated by masterloop
        try:
            cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        except: cards = 0
            
        # Get recent episodes
        try:
            episodes = conn.execute("SELECT * FROM episodes ORDER BY id DESC LIMIT 5").fetchall()
        except: episodes = []
        
        return jsonify({
            "status": "MASTERLOOP_ACTIVE",
            "cards_processed": cards,
            "recent_episodes": [dict(e) for e in episodes]
        })
    except Exception as e:
        import sys, traceback
        print(f"Stats Error: {e}", file=sys.stderr)
        return jsonify({
            "status": "INITIALIZING", 
            "cards_processed": 0, 
            "recent_episodes": []
        })
    finally:
        if 'conn' in locals(): conn.close()

@app.route('/api/narrative/latest')
def latest_narrative():
    try:
        conn = get_db()
        # Join predictions with episodes to get the latest completed analysis
        query = """
            SELECT 
                p.hypothesis as title,
                p.confidence,
                p.rationale,
                e.ts as timestamp
            FROM predictions p
            JOIN episodes e ON p.episode_id = e.id
            ORDER BY e.ts DESC
            LIMIT 10
        """
        rows = conn.execute(query).fetchall()
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        print(f"Narrative Error: {e}")
        return jsonify([])
    finally:
        if 'conn' in locals(): conn.close()

@app.route('/api/stream')
def stream():
    def event_stream():
        q = queue.Queue(maxsize=100)
        SSE_QUEUES.append(q)
        try:
            # Send initial state
            initial_data = json.dumps(LATEST_STATE)
            yield f"event: INITIAL_STATE\ndata: {initial_data}\n\n"
            
            # Keep connection alive
            while True:
                msg = q.get()
                yield msg
        except GeneratorExit:
            SSE_QUEUES.remove(q)
            
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/api/run', methods=['POST'])
def run_cycle():
    from flask import request
    data = request.json or {}
    user_request = data.get('instruction', 'Autonomous System Check')
    
    # Run in background (simple approach for now)
    def task():
        global LATEST_STATE
        print(f"🚀 Triggering Cycle: {user_request}")
        LATEST_STATE["execution_status"] = "RUNNING"
        broadcast_event("STATUS_UPDATE", {"status": "RUNNING"})
        
        try:
            # Pass broadcast_event as callback
            final_state = masterloop_orchestrator.run_cycle(
                user_request, 
                thread_id="dashboard_run",
                on_event=broadcast_event
            )
            
            # Update global state
            LATEST_STATE.update(final_state)
            LATEST_STATE["execution_status"] = "IDLE" 
            broadcast_event("STATUS_UPDATE", {"status": "IDLE"})
            broadcast_event("FINAL_STATE", final_state)
            
        except Exception as e:
            print(f"❌ Cycle Failed: {e}")
            LATEST_STATE["execution_status"] = "ERROR"
            LATEST_STATE["error"] = str(e)
            broadcast_event("ERROR", {"message": str(e)})

    threading.Thread(target=task).start()
    return jsonify({"status": "Cycle Started", "instruction": user_request})

@app.route('/api/status', methods=['GET'])
def get_status():
    global LATEST_STATE
    return jsonify(LATEST_STATE)

if __name__ == '__main__':
    # No auto-start, waiting for Dashboard trigger
    print("🧠 API READY. Listening on 5000...")
    app.run(host='0.0.0.0', port=5000, threaded=True)
