#!/usr/bin/env python3
"""
lab/langsmith_eval.py
=====================
LAB SCRIPT — LangSmith Ecosystem Setup & Verification.
SAFE: touches nothing in /core or /workflows. Pure API calls.

What this does:
  1. Verifies the API key is valid and tracing works (CREATE a test run)
  2. Lists existing prompts in LangSmith Hub (read-only - push from UI)
  3. Creates a PolySignal-Scenarios evaluation dataset (if on paid plan)
  4. Explains what to do manually for anything that needs the LangSmith UI

NOTE on lsv2_pt_* personal tokens:
  - ✅ Tracing (create runs, stream node events)
  - ✅ List/read prompts from Hub
  - ✅ Playground
  - ❌ push_prompt (calls /settings endpoint, forbidden on personal tokens)
  - ❌ create_dataset via API (403 on free tier)
  → For prompts and datasets: use the LangSmith UI at smith.langchain.com

Run as:
  cd /path/to/polysignal-engine
  LANGCHAIN_TRACING_V2=true LANGCHAIN_PROJECT=PolySignal-OS-dev python3 lab/langsmith_eval.py
"""

import os
import sys
import json
import time

# ── Guard: remove lab/ from sys.path to avoid signal.py shadowing stdlib ──────
# Per PROGRESS.md, lab/signal.py is an artifact awaiting deletion.
_lab_dir = os.path.dirname(os.path.abspath(__file__))
if _lab_dir in sys.path:
    sys.path.remove(_lab_dir)

# ── Environment ───────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Force to dev project so these traces never appear in production
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT_DEV", "PolySignal-OS-dev")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")

# ── LangSmith Client (EU Region) ──────────────────────────────────────────────
from langsmith import Client
ls = Client(api_url=os.getenv("LANGCHAIN_ENDPOINT", "https://eu.api.smith.langchain.com"))

REQUIRED_KEYS = {"tool", "command", "workspace", "reasoning"}

SAMPLE_SCENARIOS = [
    {
        "input": {
            "user_request": "Run signal scan",
            "obs_text": json.dumps([{
                "title": "Bitcoin above $100k?",
                "market_id": "btc-100k",
                "probability": 0.72,
                "change_24h": 0.08,
            }]),
        },
        "expected_keys": list(REQUIRED_KEYS),
        "metadata": {"scenario": "btc_bullish", "difficulty": "easy"},
    },
    {
        "input": {
            "user_request": "Check system health",
            "obs_text": json.dumps([]),
        },
        "expected_keys": list(REQUIRED_KEYS),
        "metadata": {"scenario": "no_signals_health", "difficulty": "easy"},
    },
    {
        "input": {
            "user_request": "List workspace files",
            "obs_text": json.dumps([{
                "title": "ETH below $2k?",
                "market_id": "eth-2k",
                "probability": 0.61,
                "change_24h": -0.12,
            }]),
        },
        "expected_keys": list(REQUIRED_KEYS),
        "metadata": {"scenario": "eth_bearish", "difficulty": "medium"},
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Verify API Key + Tracing
# ─────────────────────────────────────────────────────────────────────────────

def verify_tracing():
    print("\n[1/3] Verifying API key and tracing...")
    import uuid
    try:
        run_id = str(uuid.uuid4())
        ls.create_run(
            id=run_id,
            name="polysignal-smoke-test",
            run_type="chain",
            inputs={"test": "LangSmith tracing verification for PolySignal-OS"},
            tags=["smoke-test", "polysignal"],
            extra={"metadata": {"cycle": 0, "node": "smoke_test"}},
        )
        time.sleep(0.5)
        ls.update_run(
            run_id,
            outputs={"result": "✅ Tracing confirmed working"},
            end_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
        print(f"  ✅ API key valid — test run created")
        print(f"  → View at: eu.smith.langchain.com → Projects → PolySignal-OS-dev")
        return True
    except Exception as e:
        print(f"  ✗ Tracing verification failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Prompt Hub: List what's there + print manual push instructions
# Note: push_prompt requires /settings endpoint, forbidden on lsv2_pt_* tokens.
# Manage prompts via UI: smith.langchain.com → Prompts → New
# ─────────────────────────────────────────────────────────────────────────────

DRAFT_PROMPT_CONTENT = """\
You are the PolySignal OS planning agent. Apply RenTec absolute empiricism.
User Request: "{user_request}"

MARKET INTELLIGENCE:
{obs_text}

Translate user intent into a precise shell command. Reply ONLY with valid JSON:
{{
  "tool": "openclaw_execute",
  "command": "<exact shell command>",
  "workspace": "/mnt/workplace",
  "reasoning": "<1 sentence explanation citing the data>"
}}"""


def setup_prompt_hub():
    print("\n[2/3] Prompt Hub setup...")
    try:
        # list_prompts returns (key, value) tuples in this SDK version
        all_prompts = list(ls.list_prompts(limit=50, is_public=False))
        # Handle both tuple and object return formats
        def get_handle(p):
            if isinstance(p, tuple):
                items = p[1] if len(p) > 1 else []
                return [x.repo_handle for x in items if hasattr(x, 'repo_handle')]
            return [p.repo_handle] if hasattr(p, 'repo_handle') else []
        
        handles = [h for p in all_prompts for h in get_handle(p)]
        mine = [h for h in handles if 'polysignal' in h.lower()]
        
        if mine:
            print(f"  ✅ Found existing prompt(s): {mine}")
        else:
            print("  ℹ No polysignal prompts found in your Hub yet.")
            print("  → Create via UI (personal tokens cannot call /settings):")
            print("    1. Open eu.smith.langchain.com → Prompts → + New")
            print("    2. Name: polysignal-draft  (set to Private)")
            print("    3. Paste the draft_node template from workflows/masterloop.py")
    except Exception as e:
        print(f"  ⚠ Could not list prompts: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Datasets: create via API (paid plan) or print UI instructions
# ─────────────────────────────────────────────────────────────────────────────

DATASET_NAME = "PolySignal-Scenarios"


def setup_dataset():
    print(f"\n[3/3] Dataset '{DATASET_NAME}' setup...")

    # Try API first (works on paid plans)
    try:
        existing = [d for d in ls.list_datasets() if d.name == DATASET_NAME]
        if existing:
            print(f"  ✅ Dataset already exists (id={existing[0].id})")
            return

        dataset = ls.create_dataset(
            DATASET_NAME,
            description="Synthetic market scenarios for structural evaluation of PolySignal-OS draft_node.",
        )
        for s in SAMPLE_SCENARIOS:
            ls.create_example(
                inputs=s["input"],
                outputs={"expected_keys": s["expected_keys"]},
                metadata=s["metadata"],
                dataset_id=dataset.id,
            )
        print(f"  ✅ Dataset created via API — {len(SAMPLE_SCENARIOS)} scenarios added")
        print(f"  → View at: smith.langchain.com → Datasets → {DATASET_NAME}")

    except Exception as e:
        if "403" in str(e) or "Forbidden" in str(e):
            print("  ℹ Dataset API requires paid plan — create via UI instead:")
            print("    1. Open smith.langchain.com → Datasets → + New Dataset")
            print(f"   2. Name: {DATASET_NAME}")
            print("    3. Add the 3 example scenarios below (CSV import):")
            print()
            print("Scenario CSV:")
            print("user_request,obs_text")
            for s in SAMPLE_SCENARIOS:
                obs = s["input"]["obs_text"].replace('"', '""')
                print(f'  "{s["input"]["user_request"]}","{obs}"')
        else:
            print(f"  ✗ Dataset setup failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("PolySignal-OS — LangSmith Ecosystem Verification")
    print(f"Project : {os.environ.get('LANGCHAIN_PROJECT')}")
    print(f"Key     : {LANGCHAIN_API_KEY[:12]}...{LANGCHAIN_API_KEY[-4:]}")
    print("=" * 60)

    ok = verify_tracing()
    setup_prompt_hub()
    setup_dataset()

    print("\n" + "=" * 60)
    if ok:
        print("✅ LangSmith is live. Summary:")
        print("  → Tracing : smith.langchain.com → Projects → PolySignal-OS-dev")
        print("  → Prompts : smith.langchain.com → Prompts → + New (manual push)")
        print("  → Dataset : smith.langchain.com → Datasets (manual or paid API)")
        print()
        print("  To trace production runs:")
        print("    LANGCHAIN_TRACING_V2=true python3 workflows/masterloop.py")
        print("  Toggle LANGCHAIN_TRACING_V2=false in .env when done debugging.")
    else:
        print("✗ API key issue — check LANGCHAIN_API_KEY in .env")
    print("=" * 60)
