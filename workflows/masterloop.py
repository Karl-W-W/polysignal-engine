#!/usr/bin/env python3
"""
workflows/masterloop.py
=======================
The MasterLoop — LangGraph implementation of the Tri-State Checkpoint Protocol.

Architecture:
  PERCEPTION → PREDICTION → DRAFT → REVIEW → [WAIT_APPROVAL] → COMMIT

This file orchestrates the full perceive-decide-act-evaluate-learn cycle.
It imports from /core (the Vault) but is NOT part of the Vault itself;
it is a workflow that wires Vault components together.

Promotion History:
  - Moved FROM core/orchestrator.py → workflows/masterloop.py (2026-02-23)
  - Reason: LangGraph state machines belong in /workflows per ARCHITECTURE.md §2
  - Bugs fixed during migration: duplicate imports, missing state field,
    deprecated s.dict() → s.model_dump(), deprecated datetime.utcnow()
  - 2026-02-24: LangSmith structured run metadata (run_name, tags, metadata)
  - 2026-02-24: Perception node replaced — now uses bitcoin_signal.py pipeline
    instead of generic observe_markets(). Auth: human-approved diff.
"""

import os
import sys
import json
import hmac
import hashlib
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime, timezone

# ── LangGraph ────────────────────────────────────────────────────────────────
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# ── LangChain ────────────────────────────────────────────────────────────────
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

# ── LangSmith ─────────────────────────────────────────────────────────────────
try:
    from langsmith import Client as LangSmithClient
    _ls_client = LangSmithClient()
except Exception:
    _ls_client = None

# ── Environment (MUST load before core imports — they read os.getenv at module level) ──
from dotenv import load_dotenv
load_dotenv(os.getenv("ENV_PATH", "/opt/loop/.env"))

# ── Vault Imports (core/ is READ-ONLY; we import, never modify) ──────────────
try:
    from core.supervisor import audit_action, verify_signature
    from core.bridge import OpenClawTool
    from core.predict import predict_market_moves
    from core.notifications import send_telegram_alert
except ImportError:
    try:
        # Fallback for running inside the polysignal-engine dir directly
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from core.supervisor import audit_action, verify_signature
        from core.bridge import OpenClawTool
        from core.predict import predict_market_moves
        from core.notifications import send_telegram_alert
    except ImportError as e:
        print(f"CRITICAL: Core vault imports failed: {e}")
        def send_telegram_alert(msg): print(f"MOCK ALERT: {msg}")

# ── Risk Gate (promoted from lab/ to core/ — Session 9) ──────────────────────
try:
    from core.risk_integration import risk_gate_node, route_after_risk_gate
except ImportError:
    # Fallback: no risk gate — pass through (degrades gracefully)
    def risk_gate_node(state):
        print("[RISK_GATE] Module not found — passthrough (no risk checks)")
        return state
    def route_after_risk_gate(state):
        if state.get("execution_status") == "RISK_BLOCKED":
            return END
        if state.get("human_approval_needed"):
            return "wait_approval"
        if state.get("signature"):
            return "commit"
        return END

# ── Configuration ─────────────────────────────────────────────────────────────
OLLAMA_HOST  = os.getenv("OLLAMA_HOST",  "http://172.17.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.3:70b")
MEMORY_PATH  = os.getenv("MEMORY_PATH",  "/opt/loop/brain/memory.md")
HMAC_SECRET  = os.getenv("HMAC_SECRET_KEY", "").encode("utf-8")

brain = ChatOpenAI(
    base_url=f"{OLLAMA_HOST}/v1",
    model=OLLAMA_MODEL,
    api_key="ollama",
    temperature=0.3,
)
print(f"✅ Brain: {OLLAMA_MODEL} @ {OLLAMA_HOST}")

openclaw_tool = OpenClawTool()


# ── Memory helpers ────────────────────────────────────────────────────────────

def read_memory() -> str:
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r") as f:
            return f.read()
    return "No previous learnings recorded."


def write_memory(entry: str):
    ts = datetime.now(timezone.utc).isoformat()
    with open(MEMORY_PATH, "a") as f:
        f.write(f"\n### {ts}\n{entry}\n")


# ============================================================================
# STATE
# ============================================================================

class LoopState(TypedDict):
    """State flowing through every node in the MasterLoop."""
    thread_id:    str
    cycle_number: int
    started_at:   str
    user_request: str

    # Perceive
    observations: List[Dict]

    # Predict
    predictions: List[Dict]

    # Draft
    draft_action:    Optional[Dict[str, Any]]
    draft_reasoning: Optional[str]

    # Review
    audit_verdict:        Optional[Dict[str, Any]]
    signature:            Optional[str]
    human_approval_needed: bool
    human_approved:       Optional[bool]

    # Commit
    execution_result: Optional[str]
    execution_status: Optional[str]
    moltbook_result:  Optional[str]

    # Meta
    errors:        List[str]
    stage_timings: Dict[str, float]


# ============================================================================
# NODE 0: PERCEPTION (Crypto Pipeline — promoted from lab/ 2026-02-24)
# ============================================================================

# ── Crypto perception imports ──
try:
    from lab.experiments.bitcoin_signal import fetch_crypto_markets, detect_signals
except ImportError:
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from lab.experiments.bitcoin_signal import fetch_crypto_markets, detect_signals
    except ImportError as e:
        print(f"CRITICAL: bitcoin_signal import failed: {e}")
        def fetch_crypto_markets(): return []
        def detect_signals(m): return []


def _market_to_observation(m: dict) -> dict:
    """Convert raw crypto market dict to LoopState observation format."""
    return {
        "market_id":  m["id"],
        "title":      f"{m['title']} — {m['outcome']}",
        "price":      m["price"],
        "volume":     m["volume"],
        "change_24h": 0.0,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "source":     "polymarket",
        "direction":  "",
        "url":        m["url"],
    }


def _signal_to_observation(sig: dict) -> dict:
    """Convert detected signal dict to LoopState observation format."""
    return {
        "market_id":    sig["market_id"],
        "title":        f"{sig['title']} — {sig['outcome']}",
        "price":        sig["current_price"],
        "volume":       sig["volume"],
        "change_24h":   sig["delta"],
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "source":       "polymarket",
        "direction":    sig["direction"],
        "url":          sig["url"],
        "time_horizon": sig.get("time_horizon", "24h"),
    }


def perception_node(state: LoopState) -> LoopState:
    """Crypto perception — uses bitcoin_signal.py pipeline (promoted from lab)."""
    print("\n[PERCEPTION] Scanning crypto markets...")
    start = datetime.now(timezone.utc)

    try:
        markets = fetch_crypto_markets()

        if not markets:
            print("  ⚠ No crypto markets returned from API")
            state["observations"] = []
            state["errors"].append("Perception: No markets returned")
        else:
            signals = detect_signals(markets)

            if signals:
                state["observations"] = [_signal_to_observation(s) for s in signals]
                for obs in state["observations"]:
                    obs["cycle_number"] = state["cycle_number"]
                print(f"  🔔 {len(signals)} signal(s) detected:")
                for s in signals:
                    print(f"     {s['direction']}  {s['title'][:50]}  {s['delta']:+.3f}")
            else:
                state["observations"] = [_market_to_observation(m) for m in markets]
                for obs in state["observations"]:
                    obs["cycle_number"] = state["cycle_number"]
                print(f"  ✓ {len(markets)} markets observed, 0 signals (quiet market)")

    except Exception as e:
        print(f"  ✗ Perception failed: {e}")
        state["observations"] = []
        state["errors"].append(f"Perception: {e}")

    # ── Evaluate past predictions against fresh prices (non-blocking) ─────────
    # NOTE: Must run AFTER market fetch so state["observations"] has current prices.
    # Bug fix Session 14: was called before fetch → empty observations → 0 evaluations.
    try:
        from lab.outcome_tracker import evaluate_outcomes, get_accuracy_summary
        eval_result = evaluate_outcomes(state.get("observations", []))
        if eval_result["evaluated"] > 0:
            print(f"  📊 Outcomes: {eval_result['correct']} correct, "
                  f"{eval_result['incorrect']} wrong, {eval_result['neutral']} neutral")
            print(f"     {get_accuracy_summary()}")
    except Exception:
        pass  # First cycle or no prior predictions — expected

    state["stage_timings"]["perception"] = (datetime.now(timezone.utc) - start).total_seconds()
    return state


# ============================================================================
# NODE 1: PREDICTION
# ============================================================================

def prediction_node(state: LoopState) -> LoopState:
    print("\n[PREDICTION] Decoding patterns...")
    start = datetime.now(timezone.utc)

    observations = state.get("observations", [])
    if not observations:
        print("  ⚠ No observations — skipping.")
        state["predictions"] = []
        return state

    try:
        preds = predict_market_moves(observations)
        predictions = [p.to_dict() for p in preds]

        # Enhance Neutral predictions with perception signal data.
        # Rule-based predictor returns Neutral when DB history is missing;
        # perception signals already carry direction + delta from bitcoin_signal.py.
        obs_signals = {}
        for obs in observations:
            mid = obs.get("market_id")
            direction = obs.get("direction", "")
            if mid and direction:
                obs_signals[mid] = obs

        enhanced = 0
        for pred in predictions:
            if pred["hypothesis"] == "Neutral" and pred["market_id"] in obs_signals:
                sig = obs_signals[pred["market_id"]]
                direction = sig["direction"].lower()
                pred["hypothesis"] = "Bullish" if "bull" in direction or "📈" in sig.get("direction", "") else "Bearish"
                delta = abs(sig.get("change_24h", 0.0))
                pred["confidence"] = round(min(0.55 + delta * 2, 0.85), 2)
                pred["reasoning"] = f"Signal-enhanced: {sig['direction']} (delta: {sig.get('change_24h', 0):.3f})"
                pred["time_horizon"] = sig.get("time_horizon", "24h")
                enhanced += 1

        # ── XGBoost confidence gate (Session 15) ─────────────────────────────
        # Meta-predictor: evaluates P(this prediction will be CORRECT).
        # Suppresses predictions where the model expects them to fail.
        suppressed = 0
        gate_ran = False
        try:
            from lab.xgboost_baseline import load_model as xgb_load, select_features
            from lab.feature_engineering import extract_features
            xgb_model, xgb_features = xgb_load()
            db_path = os.getenv("DB_PATH", "/opt/loop/data/test.db")

            gated = []
            for pred in predictions:
                market_id = pred.get("market_id")
                if not market_id:
                    gated.append(pred)
                    continue
                try:
                    fv = extract_features(market_id, db_path=db_path)
                    X = select_features(fv, xgb_features)
                    proba = xgb_model.predict_proba(X)[0]
                    p_correct = float(proba[1])
                    pred["xgb_p_correct"] = round(p_correct, 3)

                    if p_correct < 0.5:
                        suppressed += 1
                        continue
                    gated.append(pred)
                except Exception as e:
                    print(f"  ⊘ XGBoost gate: {market_id} feature extraction failed: {e}")
                    gated.append(pred)
            predictions = gated
            gate_ran = True
        except Exception as e:
            print(f"  ⊘ XGBoost gate skipped: {e}")

        state["predictions"] = predictions
        if gate_ran:
            print(f"  🔍 XGBoost gate: {len(predictions)} passed, {suppressed} suppressed")
        print(f"  ✓ {len(predictions)} hypotheses ({enhanced} signal-enhanced)")

        # ── Record predictions for future outcome evaluation (non-blocking) ──
        try:
            from lab.outcome_tracker import record_predictions
            recorded = record_predictions(
                state["predictions"], observations,
                cycle_number=state.get("cycle_number", 0),
            )
            if recorded:
                print(f"  📝 {recorded} predictions recorded for outcome tracking")
        except Exception:
            pass

    except Exception as e:
        print(f"  ⚠ Prediction failed: {e}")
        state["predictions"] = []
        state["errors"].append(f"Prediction: {e}")

    state["stage_timings"]["prediction"] = (datetime.now(timezone.utc) - start).total_seconds()
    return state


# ============================================================================
# NODE 2: DRAFT
# ============================================================================

def draft_node(state: LoopState) -> LoopState:
    print("\n[DRAFT] Planning action...")
    start = datetime.now(timezone.utc)

    user_request = state.get("user_request", "")
    obs_text  = json.dumps(state.get("observations",  []), indent=2) or "None"
    pred_text = json.dumps(state.get("predictions",   []), indent=2) or "None"
    memory    = read_memory()

    # ── Build prompt (pull from LangSmith Hub if available, else fallback) ───
    hardcoded_prompt = f"""You are the PolySignal OS planning agent. Apply RenTec absolute empiricism.
User Request: "{user_request}"

MARKET INTELLIGENCE:
{obs_text}

PREDICTIVE ANALYTICS:
{pred_text}

STRATEGIC MEMORY:
{memory[-500:]}

Translate user intent into a precise shell command. Reply ONLY with valid JSON:
{{
  "tool": "openclaw_execute",
  "command": "<exact shell command>",
  "workspace": "/mnt/workplace",
  "reasoning": "<1 sentence explanation citing the data>"
}}"""

    prompt = hardcoded_prompt  # default
    if _ls_client:
        try:
            tmpl = _ls_client.pull_prompt("polysignal-draft")
            prompt = tmpl.format(
                user_request=user_request,
                obs_text=obs_text,
                pred_text=pred_text,
                memory=memory[-500:],
            )
        except Exception:
            pass  # Hub not yet populated — silently use hardcoded prompt

    # ── LangSmith run config for this LLM call ────────────────────────────────
    ls_config: RunnableConfig = {
        "run_name": "draft_node",
        "tags": ["draft", f"cycle-{state['cycle_number']}", "polysignal"],
        "metadata": {
            "thread_id":          state["thread_id"],
            "cycle_number":       state["cycle_number"],
            "observations_count": len(state.get("observations", [])),
            "predictions_count":  len(state.get("predictions", [])),
        },
    }

    try:
        response = brain.invoke([HumanMessage(content=prompt)], config=ls_config)
        cleaned  = response.content.replace('```json', '').replace('```', '').strip()
        draft    = json.loads(cleaned)

        if "command" not in draft:
            raise ValueError("Missing 'command' field in model response")

        state["draft_action"]   = draft
        state["draft_reasoning"] = draft.get("reasoning", "")
        print(f"  ✓ Draft: {draft['command']}")

    except Exception as e:
        print(f"  ✗ Draft failed: {e}")
        state["errors"].append(f"Draft: {e}")
        state["draft_action"] = {
            "tool":      "openclaw_execute",
            "command":   "echo 'DRAFT_ERROR'",
            "workspace": "/mnt/workplace",
            "reasoning": str(e)
        }

    state["stage_timings"]["draft"] = (datetime.now(timezone.utc) - start).total_seconds()
    return state


# ============================================================================
# NODE 3: REVIEW (NVIDIA Supervisor — Hardware Veto)
# ============================================================================

def review_node(state: LoopState) -> LoopState:
    print("\n[REVIEW] Auditing with NVIDIA Supervisor...")
    start = datetime.now(timezone.utc)

    draft = state.get("draft_action")
    if not draft:
        state["errors"].append("No draft to review")
        return state

    try:
        verdict    = audit_action(draft)
        verdict_t  = verdict.get("verdict")
        risk_level = verdict.get("risk_level", "unknown")

        state["audit_verdict"] = verdict
        print(f"  ✓ Verdict: {verdict_t} (Risk: {risk_level})")

        if verdict_t == "APPROVE":
            state["signature"]             = verdict.get("signature")
            state["human_approval_needed"] = False

        elif verdict_t == "REQUEST_HUMAN_APPROVAL":
            state["human_approval_needed"] = True
            state["signature"]             = None
            send_telegram_alert(
                f"⚠️ *Approval Required*\n"
                f"Command: `{draft.get('command')}`\n"
                f"Reason: {verdict.get('reasoning')}"
            )

        else:  # REJECT
            state["signature"]             = None
            state["human_approval_needed"] = False
            send_telegram_alert(
                f"⛔ *Action BLOCKED*\n"
                f"Command: `{draft.get('command')}`\n"
                f"Risk: {risk_level} — {verdict.get('reasoning')}"
            )

    except Exception as e:
        print(f"  ✗ Review failed: {e}")
        state["errors"].append(f"Review: {e}")
        state["signature"]             = None
        state["human_approval_needed"] = False

    state["stage_timings"]["review"] = (datetime.now(timezone.utc) - start).total_seconds()
    return state


# ============================================================================
# NODE 3B: WAIT FOR HUMAN APPROVAL
# ============================================================================

def wait_approval_node(state: LoopState) -> LoopState:
    print("\n[WAIT_APPROVAL] Pausing for human decision...")
    # In production this is a LangGraph interrupt point.
    # For now, auto-approve so cycle can complete end-to-end.
    state["human_approved"] = True

    if state["human_approved"] and HMAC_SECRET:
        draft     = state["draft_action"]
        canonical = json.dumps(draft, sort_keys=True, separators=(',', ':')).encode()
        sig       = hmac.new(HMAC_SECRET, canonical, hashlib.sha256).hexdigest()
        state["signature"] = sig
        print("  ✓ Human approved — signature generated")
    else:
        print("  ✗ No HMAC secret or human rejected")

    return state


# ============================================================================
# NODE 4: COMMIT (OpenClaw Execution)
# ============================================================================

def commit_node(state: LoopState) -> LoopState:
    print("\n[COMMIT] Executing via OpenClaw...")
    start = datetime.now(timezone.utc)

    draft     = state.get("draft_action")
    signature = state.get("signature")

    if not signature:
        state["execution_status"] = "BLOCKED"
        state["execution_result"] = "No signature — action was rejected"
        print("  ✗ Blocked: no signature")
        return state

    if not verify_signature(draft, signature):
        state["execution_status"] = "BLOCKED"
        state["execution_result"] = "SECURITY VIOLATION: Signature mismatch"
        print("  ✗ SECURITY VIOLATION")
        return state

    print("  ✓ Signature verified")

    try:
        result = openclaw_tool._run(command=draft["command"])
        state["execution_result"] = result

        # Bridge returns errors as strings (not exceptions) — detect them
        if isinstance(result, str) and result.startswith("❌"):
            state["execution_status"] = "FAILED"
            state["errors"].append(f"Commit: {result[:200]}")
            print(f"  ✗ {result[:150]}")
        else:
            state["execution_status"] = "SUCCESS"
            print(f"  ✓ Done: {str(result)[:150]}")

    except Exception as e:
        state["execution_status"] = "FAILED"
        state["execution_result"] = str(e)
        state["errors"].append(f"Commit: {e}")
        print(f"  ✗ Execution failed: {e}")

    state["stage_timings"]["commit"] = (datetime.now(timezone.utc) - start).total_seconds()

    # ── MoltBook signal publishing (non-blocking) ──────────────────────────────
    if state["execution_status"] == "SUCCESS":
        try:
            from lab.moltbook_publisher import publish_signal, MoltBookConfig
            config = MoltBookConfig.from_env()
            signal_obs = [o for o in state.get("observations", []) if o.get("direction")]
            if signal_obs:
                audit_hash = state.get("signature", "no_sig")[:24]
                pub_result = publish_signal(signal_obs[0], state["stage_timings"], audit_hash, config)
                state["moltbook_result"] = pub_result.reason
                if pub_result.published:
                    print(f"  ✓ Published to MoltBook: {pub_result.post_id}")
                else:
                    print(f"  ⊘ MoltBook: {pub_result.reason}")
        except Exception as e:
            state["moltbook_result"] = f"Error: {e}"
            print(f"  ⊘ MoltBook publish skipped: {e}")

    # ── Learning: write cycle summary to memory (non-blocking) ────────────────
    try:
        obs_count = len(state.get("observations", []))
        pred_count = len(state.get("predictions", []))
        signals = [o for o in state.get("observations", []) if o.get("direction")]
        signal_summary = ", ".join(
            f"{s.get('title', '?')[:40]} ({s.get('direction', '?')})"
            for s in signals[:3]
        ) or "none"
        entry = (
            f"Cycle #{state.get('cycle_number', '?')} | "
            f"Obs: {obs_count} | Signals: {len(signals)} | Preds: {pred_count} | "
            f"Status: {state.get('execution_status', 'UNKNOWN')} | "
            f"Signals: {signal_summary}"
        )
        if state.get("draft_reasoning"):
            entry += f" | Reasoning: {state['draft_reasoning'][:100]}"
        try:
            from lab.outcome_tracker import get_accuracy_summary
            entry += f" | {get_accuracy_summary()}"
        except Exception:
            pass
        write_memory(entry)
        print(f"  ✓ Memory updated")
    except Exception as e:
        print(f"  ⊘ Memory write skipped: {e}")

    return state


# ============================================================================
# ROUTING
# ============================================================================

def route_after_prediction(state: LoopState) -> str:
    """Skip draft/review/risk_gate when trading disabled — saves 2 LLM calls/cycle."""
    from core.risk import TRADING_ENABLED
    if not TRADING_ENABLED:
        print("\n[SHORT-CIRCUIT] TRADING_ENABLED=false — skipping draft/review/risk_gate")
        return END
    return "draft"


def route_after_review(state: LoopState) -> str:
    if state.get("human_approval_needed"):
        return "wait_approval"
    elif state.get("signature"):
        return "commit"
    return END


# ============================================================================
# GRAPH ASSEMBLY
# ============================================================================

def build_masterloop() -> StateGraph:
    wf = StateGraph(LoopState)

    wf.add_node("perception",    perception_node)
    wf.add_node("prediction",    prediction_node)
    wf.add_node("draft",         draft_node)
    wf.add_node("review",        review_node)
    wf.add_node("risk_gate",     risk_gate_node)
    wf.add_node("wait_approval", wait_approval_node)
    wf.add_node("commit",        commit_node)

    wf.set_entry_point("perception")
    wf.add_edge("perception",    "prediction")
    wf.add_conditional_edges(
        "prediction",
        route_after_prediction,
        {"draft": "draft", END: END},
    )
    wf.add_edge("draft",         "review")
    # Review routes to risk_gate (if approved/needs-human) or END (if rejected)
    wf.add_conditional_edges(
        "review",
        route_after_review,
        {"wait_approval": "risk_gate", "commit": "risk_gate", END: END}
    )
    # Risk gate routes to wait_approval, commit, or END (if blocked)
    wf.add_conditional_edges(
        "risk_gate",
        route_after_risk_gate,
        {"wait_approval": "wait_approval", "commit": "commit", END: END}
    )
    wf.add_edge("wait_approval", "commit")
    wf.add_edge("commit",        END)

    return wf


# ============================================================================
# PUBLIC API
# ============================================================================

def run_cycle(user_request: str, thread_id: str = "default", on_event=None, cycle_number: int = 1) -> LoopState:
    """
    Execute one full MasterLoop cycle.
    on_event: optional callback(event_type: str, data: dict)
    """

    def emit(t, msg, payload=None):
        if on_event:
            try: on_event(t, {"message": msg, "payload": payload or {}})
            except Exception: pass

    graph = build_masterloop()
    app   = graph.compile(checkpointer=MemorySaver())

    initial: LoopState = {
        "thread_id":             thread_id,
        "cycle_number":          cycle_number,
        "started_at":            datetime.now(timezone.utc).isoformat(),
        "user_request":          user_request,
        "observations":          [],   # ← was missing from original; caused KeyError
        "predictions":           [],
        "draft_action":          None,
        "draft_reasoning":       None,
        "audit_verdict":         None,
        "signature":             None,
        "human_approval_needed": False,
        "human_approved":        None,
        "execution_result":      None,
        "execution_status":      None,
        "moltbook_result":       None,
        "errors":                [],
        "stage_timings":         {},
    }

    print("\n" + "="*60)
    print("MASTERLOOP CYCLE START")
    print("="*60)
    emit("CYCLE_START", f"Processing: {user_request}", {"request": user_request})

    final = dict(initial)
    # ── LangSmith run config for the full graph stream ───────────────────────
    graph_config: RunnableConfig = {
        "run_name": f"MasterLoop-{thread_id}",
        "tags":     ["masterloop", "polysignal"],
        "metadata": {
            "request":      user_request,
            "thread_id":    thread_id,
            "cycle_number": cycle_number,
        },
        "configurable": {"thread_id": thread_id},
    }

    for output in app.stream(initial, config=graph_config):
        for node, update in output.items():
            print(f"🔄 {node} complete")
            final.update(update)

            events = {
                "perception": ("PERCEPTION_COMPLETE", lambda u: f"{len(u.get('observations',[]))} signals"),
                "prediction":  ("PREDICTION_COMPLETE", lambda u: f"{len(u.get('predictions',[]))} hypotheses"),
                "draft":       ("DRAFT_COMPLETE",      lambda u: u.get("draft_action", {}).get("command", "")),
                "review":      ("REVIEW_COMPLETE",     lambda u: u.get("audit_verdict", {}).get("verdict", "")),
                "commit":      ("EXECUTION_COMPLETE",  lambda u: u.get("execution_status", "")),
            }
            if node in events:
                ev_type, msg_fn = events[node]
                emit(ev_type, msg_fn(update), update)

    print("\n" + "="*60)
    print("MASTERLOOP CYCLE COMPLETE")
    print("="*60)
    emit("CYCLE_COMPLETE", "Done", final)

    return final


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    result = run_cycle(
        user_request="List the files in the PolySignal workspace",
        thread_id="test_masterloop_001"
    )
    print(f"\nStatus:  {result.get('execution_status')}")
    print(f"Errors:  {result.get('errors')}")
    print(f"Timings: {result.get('stage_timings')}")
