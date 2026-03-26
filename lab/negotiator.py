#!/usr/bin/env python3
"""
lab/negotiator.py
==================
Level 2 Negotiator of the Hierarchical Agent Stack.
Runs on OpenShell (Security hardened).
Role: Validates Sentinel candidates and triggers Strategist escalation.
"""

import os
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

CANDIDATES_PATH = Path("lab/candidates.json")
DEPLOY_TRIGGER = Path("lab/.deploy-trigger")
NEGOTIATOR_LOG = Path("lab/.negotiator-log")

def check_candidates():
    if not CANDIDATES_PATH.exists():
        return

    try:
        with open(CANDIDATES_PATH, "r") as f:
            candidates = json.load(f)
    except Exception as e:
        print(f"Error reading candidates: {e}")
        return

    # High-confidence threshold for escalation
    ESCALATION_THRESHOLD = 0.85
    
    for c in candidates:
        if c.get("confidence", 0) >= ESCALATION_THRESHOLD:
            escalate(c)

def escalate(candidate):
    msg = f"Escalating candidate: {candidate['title']} (ID: {candidate['market_id']})"
    print(msg)
    
    with open(NEGOTIATOR_LOG, "a") as f:
        f.write(f"{datetime.now().isoformat()} | {msg}\n")
        
    # Trigger the Strategist (Claude Code / OpenClaw) via deploy trigger
    # This invokes a host-side handler that starts a premium session
    with open(DEPLOY_TRIGGER, "w") as f:
        f.write(f"escalate {candidate['market_id']} {datetime.now().isoformat()}")

def main():
    print("Negotiator starting monitor loop...")
    while True:
        check_candidates()
        time.sleep(60) # Watch every minute

if __name__ == "__main__":
    main()
