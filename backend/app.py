import threading
from flask import Flask, jsonify
from flask_cors import CORS
import masterloop  # The LangGraph Brain
import sqlite3
import os

app = Flask(__name__)
CORS(app)

DB_PATH = "/app/data/polysignal.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/health')
def health():
    return jsonify({'status': 'operational', 'brain': 'LangGraph MasterLoop'})

@app.route('/api/system/stats')
def stats():
    try:
        conn = get_db()
        # Get stats from new tables populated by masterloop
        cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        # Get recent episodes
        episodes = conn.execute("SELECT * FROM episodes ORDER BY id DESC LIMIT 5").fetchall()
        
        return jsonify({
            "status": "MASTERLOOP_ACTIVE",
            "cards_processed": cards,
            "recent_episodes": [dict(e) for e in episodes]
        })
    except Exception as e:
        print(f"Stats Error: {e}")
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

if __name__ == '__main__':
    # Start the MasterLoop in a background thread
    print("🧠 STARTING CORTEX...")
    threading.Thread(target=masterloop.autonomous_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
