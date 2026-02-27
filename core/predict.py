import sqlite3
import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

# ============================================================================
# CONFIGURATION
# ============================================================================

DB_PATH = os.getenv("DB_PATH", "/data/polysignal.db")
MEMORY_PATH = os.getenv("MEMORY_PATH", "/opt/loop/brain/memory.md")

@dataclass
class Prediction:
    market_id: str
    hypothesis: str  # e.g., "Bullish", "Bearish", "Neutral"
    confidence: float  # 0.0 to 1.0
    reasoning: str
    time_horizon: str = "24h"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def get_db_connection():
    """Connect to the PolySignal database (read-only for prediction)."""
    if not os.path.exists(DB_PATH):
        # Fallback for local testing if not in container
        local_db = "polysignal.db"
        if os.path.exists(local_db):
            return sqlite3.connect(local_db)
        return None
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def read_strategic_memory() -> str:
    """Read high-level strategic context from memory.md."""
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, "r") as f:
                # Read last 20 lines for recent context
                lines = f.readlines()
                return "".join(lines[-20:])
        except Exception as e:
            return f"Error reading memory: {e}"
    return "No strategic memory available."

def find_similar_patterns(market_id: str, current_price: float) -> List[Dict]:
    """
    Query DB for similar historical price actions.
    (MVP: comprehensive pattern matching is complex, so we stick to simple price direction)
    """
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        c = conn.cursor()
        
        # Check if we have history for this market
        c.execute('''
            SELECT price, timestamp, change_24h_at_time 
            FROM (
                SELECT price, timestamp, 
                       (price - LAG(price) OVER (ORDER BY timestamp)) as change_24h_at_time
                FROM observations 
                WHERE market_id = ?
            )
            WHERE change_24h_at_time IS NOT NULL
            ORDER BY timestamp DESC 
            LIMIT 5
        ''', (market_id,))
        
        history = [dict(row) for row in c.fetchall()]
        conn.close()
        return history
        
    except Exception as e:
        print(f"⚠ Pattern matching failed: {e}")
        if conn: conn.close()
        return []

def predict_market_moves(observations: List[Dict]) -> List[Prediction]:
    """
    Core Prediction Logic.
    Decodes market signals into probabilistic hypotheses.
    """
    predictions = []
    strategy_context = read_strategic_memory()
    
    print(f"\n[STAGE 1.5: PREDICTION] Analyze {len(observations)} signals...")
    
    for obs in observations:
        market_id     = obs.get("market_id")
        title         = obs.get("title", "Unknown Market")
        # Support both old (price/volume) and new Signal schema (current_price/volume_24h)
        current_price = obs.get("current_price") or obs.get("price", 0.5)
        volume        = obs.get("volume_24h") or obs.get("volume", 0)
        # Seed from perception signal if available
        perceived_delta = obs.get("change_since_last", 0.0)
        
        # 1. Historical Analysis
        history = find_similar_patterns(market_id, current_price)
        
        # 2. Logic Synthesis (MVP Rule-Based)
        hypothesis = "Neutral"
        confidence = 0.5
        reasoning = "Insufficient data for strong prediction."
        
        if not history:
            reasoning = "New market (Cold Start). No historical patterns found."
            confidence = 0.1
        else:
            # Simple momentum check from last few observations
            recent_moves = [h['change_24h_at_time'] for h in history if h['change_24h_at_time']]
            if recent_moves:
                avg_move = sum(recent_moves) / len(recent_moves)
                if avg_move > 0.01:
                    hypothesis = "Bullish"
                    confidence = 0.6 + min(len(history) * 0.05, 0.2)
                    reasoning = f"Positive momentum detected (Avg move: {avg_move:+.3f})"
                elif avg_move < -0.01:
                    hypothesis = "Bearish"
                    confidence = 0.6 + min(len(history) * 0.05, 0.2)
                    reasoning = f"Negative momentum detected (Avg move: {avg_move:+.3f})"
                else:
                    reasoning = "Price action is choppy/flat."
        
        # 3. Memory Context Injection
        if "aggressive" in strategy_context.lower() and confidence > 0.6:
            confidence += 0.1
            reasoning += " (Boosted by aggressive strategy)"
            
        pred = Prediction(
            market_id=market_id,
            hypothesis=hypothesis,
            confidence=round(confidence, 2),
            reasoning=reasoning
        )
        predictions.append(pred)
        print(f"  🔮 {title[:20]}... -> {hypothesis} ({confidence*100:.0f}%)")

    return predictions

if __name__ == "__main__":
    # Test Run
    mock_obs = [
        {"market_id": "test_1", "title": "Test Market Bull", "price": 0.65, "volume": 10000},
        {"market_id": "test_2", "title": "Test Market Bear", "price": 0.35, "volume": 5000}
    ]
    preds = predict_market_moves(mock_obs)
    for p in preds:
        print(p)
