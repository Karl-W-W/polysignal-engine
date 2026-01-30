import os
import json
import time
import threading
import sqlite3
import requests
import google.generativeai as genai
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime

# Configuration
app = Flask(__name__)
CORS(app)
DB_PATH = os.getenv('DB_PATH', '/data/loop.db')
GAMMA_API = "https://gamma-api.polymarket.com"
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')

# Initialize Gemini (USING STABLE MODEL)
model = None
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        # CHANGED: 'gemini-1.5-flash' -> 'gemini-2.5-flash'
        model = genai.GenerativeModel('gemini-2.5-flash', 
                                     generation_config={"response_mime_type": "application/json"})
        print("✅ Gemini Configured Successfully")
    except Exception as e:
        print(f"❌ Gemini Configuration Error: {e}")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS polymarket_markets (
                 market_id TEXT PRIMARY KEY, question TEXT, volume REAL, 
                 liquidity REAL, updated_ts TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS polymarket_signals (
                 id INTEGER PRIMARY KEY, market_id TEXT, signal_type TEXT, 
                 confidence REAL, details TEXT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS events (
                 id INTEGER PRIMARY KEY, event_type TEXT, payload TEXT, 
                 ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def search_web(query):
    if not TAVILY_API_KEY or "tvly-" not in TAVILY_API_KEY: return []
    try:
        resp = requests.post("https://api.tavily.com/search", 
                           json={"api_key": TAVILY_API_KEY, "query": query, "search_depth": "basic", "max_results": 3}, 
                           timeout=10)
        return resp.json().get('results', [])
    except Exception as e:
        print(f"Search Error: {e}")
        return []

def analyze_market(question, market_data):
    if not model: return {"summary": "Gemini Key Missing", "recommendation": "WATCH", "confidence": 0}
    
    print(f"🕵️  Gemini Analyzing: {question}")
    news = search_web(question)
    context = "\n".join([f"- {n['title']}: {n['content'][:200]}" for n in news])
    
    prompt = f"""
    Analyze this prediction market spike.
    QUESTION: {question}
    DATA: {json.dumps(market_data)}
    NEWS CONTEXT: 
    {context}
    
    Task: Explain WHY the market is moving based on the news.
    Output JSON ONLY with these keys: summary (string), reasoning (string), recommendation (WATCH/ALERT/IGNORE), confidence (0.0-1.0 float).
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini Error: {e}")
        return {"summary": "Analysis Failed", "error": str(e)}

def monitoring_loop():
    print("👁️  PolySignal Gemini Watcher Started")
    while True:
        try:
            resp = requests.get(f"{GAMMA_API}/markets?limit=50&active=true&closed=false&order=volume&ascending=false")
            markets = resp.json()
            
            conn = get_db()
            c = conn.cursor()
            
            for m in markets:
                mid = m.get('id')
                vol = float(m.get('volume', 0) or 0)
                
                # Check volume (Threshold > 1M for demo)
                if vol > 1000000:
                    c.execute("SELECT id FROM polymarket_signals WHERE market_id = ? AND ts > datetime('now', '-2 hours')", (mid,))
                    if not c.fetchone():
                        print(f"⚡ High Volume: {m.get('question')}")
                        analysis = analyze_market(m.get('question'), {'volume': vol})
                        
                        c.execute('''INSERT INTO polymarket_signals (market_id, signal_type, confidence, details) 
                                     VALUES (?, ?, ?, ?)''', 
                                     (mid, 'HIGH_VOLUME', analysis.get('confidence', 0.5), json.dumps(analysis)))
                        
                        c.execute('INSERT INTO events (event_type, payload) VALUES (?, ?)',
                                  ('GEMINI_ANALYSIS', json.dumps({'question': m.get('question'), 'result': analysis})))
                        conn.commit()
            conn.close()
        except Exception as e:
            print(f"Loop Error: {e}")
        time.sleep(120)

@app.route('/health')
def health(): return jsonify({'status': 'operational', 'brain': 'gemini-2.5-flash'})

@app.route('/api/system/stats')
def stats():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as count FROM polymarket_markets')
    m_count = c.fetchone()['count']
    c.execute('SELECT * FROM events ORDER BY ts DESC LIMIT 20')
    events = [dict(row) for row in c.fetchall()]
    return jsonify({'markets_tracked': m_count, 'recent_events': events})

if __name__ == '__main__':
    init_db()
    threading.Thread(target=monitoring_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
