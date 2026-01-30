import os
import json
import sqlite3
import time
import requests
from typing import TypedDict, Dict, List, Any, Optional
from datetime import datetime
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

# CONFIG
DB_PATH = "/app/data/polysignal.db"
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GAMMA_API = "https://gamma-api.polymarket.com/markets"

# Initialize Gemini
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp", google_api_key=GEMINI_API_KEY, temperature=0.3)

# STATE SCHEMA
class LoopState(TypedDict):
    card_id: int
    episode_id: int
    timestamp: str
    observations: List[Dict[str, Any]]
    state: Optional[Dict[str, Any]]
    predictions: List[Dict[str, Any]]
    action: Optional[Dict[str, Any]]
    outcome: Optional[Dict[str, Any]]
    errors: List[Dict[str, Any]]

# DB HELPERS
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def store_to_db(table, data):
    conn = get_db()
    keys = ', '.join(data.keys())
    q = ', '.join(['?' for _ in data])
    sql = f"INSERT INTO {table} ({keys}) VALUES ({q})"
    cur = conn.cursor()
    cur.execute(sql, list(data.values()))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

# --- NODES (The Brain Regions) ---

def perception_node(state: LoopState):
    print(f"👀 PERCEPTION: Scanning Markets...")
    
    # LIVE DATA FETCH (The Update)
    try:
        # Fetch Top 5 High-Volume Markets
        url = f"{GAMMA_API}?limit=5&active=true&closed=false&order=volume&ascending=false"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            markets = resp.json()
            # Extract only relevant signal data
            market_data = [{
                'question': m.get('question'), 
                'volume': m.get('volume'), 
                'outcome': m.get('outcomes')
            } for m in markets]
        else:
            raise Exception("API Failure")
    except Exception as e:
        print(f"⚠️ Perception Blind: {e}. Using Internal Memory.")
        # Fallback to internal DB if API fails
        conn = get_db()
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS polymarket_markets (question TEXT, volume REAL)")
        cur.execute("SELECT question, volume FROM polymarket_markets ORDER BY volume DESC LIMIT 3")
        market_data = [dict(r) for r in cur.fetchall()]
        conn.close()
    
    # FEED THE LLM
    prompt = f"""
    Act as a Hedge Fund Analyst. 
    Timestamp: {state['timestamp']}. 
    
    MARKET DATA: 
    {json.dumps(market_data)}
    
    Identify ONE significant market anomaly or high-interest event.
    Output JSON ONLY: {{ 'observations': [ {{ 'source': 'polymarket', 'data': 'The anomaly description...' }} ] }}
    """
    
    try:
        res = llm.invoke([HumanMessage(content=prompt)])
        # Clean JSON markdown if present
        text = res.content.replace('```json','').replace('```','').strip()
        obs = json.loads(text).get('observations', [])
        state['observations'] = obs
        print(f"✅ Observations: {len(obs)}")
    except Exception as e:
        print(f"Perception Error: {e}")
        state['observations'] = []
    
    return state

def prediction_node(state: LoopState):
    if not state['observations']:
        print("💤 No observations. Skipping prediction.")
        return state

    print(f"🧠 PREDICTION: Analyzing...")
    prompt = f"""
    Act as a Senior Strategist.
    Observations: {json.dumps(state['observations'])}
    
    Formulate a prediction hypothesis.
    Output JSON ONLY: {{ 'hypothesis': 'Short Title', 'confidence': 0.85, 'rationale': 'Detailed reasoning...' }}
    """
    
    try:
        res = llm.invoke([HumanMessage(content=prompt)])
        text = res.content.replace('```json','').replace('```','').strip()
        pred = json.loads(text)
        state['predictions'] = [pred]
        
        # Persist Thought
        store_to_db('predictions', {
            'episode_id': state['episode_id'], 
            'hypothesis': pred.get('hypothesis'), 
            'confidence': pred.get('confidence',0), 
            'rationale': pred.get('rationale')
        })
        print(f"✨ Hypothesis: {pred.get('hypothesis')}")
    except Exception as e:
        print(f"Prediction Error: {e}")
        state['predictions'] = []
    return state

def execution_node(state: LoopState):
    # Future: Place Orders
    state['outcome'] = {'status': 'success', 'timestamp': datetime.utcnow().isoformat()}
    return state

def dashboard_node(state: LoopState):
    conn = get_db()
    conn.execute("UPDATE cards SET status='DONE' WHERE id=?", (state['card_id'],))
    conn.commit()
    conn.close()
    return state

# --- GRAPH BUILDER ---
def build_graph():
    workflow = StateGraph(LoopState)
    workflow.add_node("perception", perception_node)
    workflow.add_node("prediction", prediction_node)
    workflow.add_node("execution", execution_node)
    workflow.add_node("dashboard", dashboard_node)
    
    workflow.set_entry_point("perception")
    workflow.add_edge("perception", "prediction")
    workflow.add_edge("prediction", "execution")
    workflow.add_edge("execution", "dashboard")
    workflow.add_edge("dashboard", END)
    
    return workflow

# --- RUNNER ---
def run_cycle(card_id):
    print(f"\n--- STARTING CYCLE: CARD {card_id} ---")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO episodes (card_id, status) VALUES (?, 'RUNNING')", (card_id,))
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    
    initial = {
        'card_id': card_id, 'episode_id': eid, 'timestamp': datetime.utcnow().isoformat(),
        'observations': [], 'predictions': [], 'errors': []
    }
    
    memory = SqliteSaver.from_conn_string(DB_PATH)
    app = build_graph().compile(checkpointer=memory)
    app.invoke(initial, config={"configurable": {"thread_id": str(card_id)}})
    print(f"--- CYCLE COMPLETE ---\n")

def autonomous_loop():
    print("🚀 MASTERLOOP ACTIVATED")
    # Ensure Tables Exist
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY, status TEXT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE TABLE IF NOT EXISTS episodes (id INTEGER PRIMARY KEY, card_id INTEGER, status TEXT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE TABLE IF NOT EXISTS predictions (id INTEGER PRIMARY KEY, episode_id INTEGER, hypothesis TEXT, confidence REAL, rationale TEXT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    # Seed initial card
    conn.execute("INSERT INTO cards (status) VALUES ('NEW')")
    conn.commit()
    conn.close()
    
    while True:
        try:
            conn = get_db()
            cur = conn.execute("SELECT id FROM cards WHERE status='NEW' LIMIT 1")
            row = cur.fetchone()
            conn.close()
            
            if row:
                run_cycle(row[0])
            else:
                # Pace the breathing (Every 60s, breathe)
                time.sleep(60)
                conn = get_db()
                conn.execute("INSERT INTO cards (status) VALUES ('NEW')")
                conn.commit()
                conn.close()
                print("🫁 New Breath (Card Created)")
                
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    autonomous_loop()
