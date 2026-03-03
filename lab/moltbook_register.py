#!/usr/bin/env python3
"""
lab/moltbook_register.py
========================
MoltBook agent registration helper.

Automates the MoltBook registration flow:
  1. POST /agents/register → gets api_key + claim_url + verification_code
  2. Prints the exact tweet Karl needs to post
  3. Waits for verification (polls /agents/status)
  4. Outputs the MOLTBOOK_JWT env var to add to .env

Usage:
    python3 lab/moltbook_register.py

After running:
    1. Post the tweet shown in the output
    2. The script will detect verification and print the env var
    3. Add the env var to /opt/loop/.env on DGX
"""

import json
import os
import sys
import time
import requests

MOLTBOOK_API = "https://www.moltbook.com/api/v1"

AGENT_NAME = "PolySignal"
AGENT_DESCRIPTION = (
    "AI-native prediction market intelligence system. "
    "Scans Polymarket via Gamma API, detects signals through a 7-node "
    "LangGraph pipeline with risk gating and HMAC audit. "
    "Publishes high-confidence crypto market signals. "
    "Built on NVIDIA DGX Spark. RenTec-inspired absolute empiricism."
)


def register_agent() -> dict:
    """Step 1: Register the agent with MoltBook."""
    print("Registering PolySignal agent with MoltBook...")
    print(f"  API: {MOLTBOOK_API}")
    print(f"  Name: {AGENT_NAME}")
    print()

    resp = requests.post(
        f"{MOLTBOOK_API}/agents/register",
        json={
            "name": AGENT_NAME,
            "description": AGENT_DESCRIPTION,
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    if resp.status_code == 200:
        data = resp.json()
        print("Registration successful!")
        return data
    elif resp.status_code == 409:
        print(f"Agent name '{AGENT_NAME}' already registered.")
        print("If you own this agent, check your existing API key.")
        print(f"Response: {resp.text}")
        sys.exit(1)
    else:
        print(f"Registration failed: {resp.status_code}")
        print(f"Response: {resp.text}")
        sys.exit(1)


def print_tweet_instructions(data: dict):
    """Step 2: Show Karl exactly what to tweet."""
    api_key = data.get("api_key", "")
    claim_url = data.get("claim_url", "")
    verification_code = data.get("verification_code", "")

    print()
    print("=" * 70)
    print("STEP 2: POST THIS TWEET (from any X/Twitter account you control)")
    print("=" * 70)
    print()
    print(f"  {verification_code}")
    print()
    print(f"  Claim URL: {claim_url}")
    print(f"  (Open this URL after posting the tweet)")
    print()
    print("=" * 70)
    print()
    print(f"  API Key (save this — it's your MOLTBOOK_JWT):")
    print(f"  {api_key}")
    print()

    return api_key


def check_claim_status(api_key: str) -> bool:
    """Step 3: Check if the agent has been claimed."""
    try:
        resp = requests.get(
            f"{MOLTBOOK_API}/agents/status",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("claimed", False) or data.get("verified", False)
    except Exception:
        pass
    return False


def wait_for_verification(api_key: str, timeout_minutes: int = 30):
    """Step 3b: Poll until verification completes."""
    print(f"Waiting for Twitter verification (timeout: {timeout_minutes}min)...")
    print("Post the tweet and open the claim URL, then come back here.")
    print()

    start = time.time()
    while time.time() - start < timeout_minutes * 60:
        if check_claim_status(api_key):
            print()
            print("VERIFICATION COMPLETE!")
            print()
            print("Add this to your DGX .env file:")
            print(f"  echo 'MOLTBOOK_JWT={api_key}' >> /opt/loop/.env")
            print()
            print("Then restart the scanner:")
            print("  systemctl --user restart polysignal-scanner")
            print()
            print("MoltBook publishing will activate automatically on next signal.")
            return True

        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(10)

    print()
    print(f"Timeout after {timeout_minutes} minutes. You can still claim later.")
    print(f"Your API key: {api_key}")
    print("Add it to .env whenever you complete the Twitter verification.")
    return False


def main():
    print("=" * 70)
    print("PolySignal — MoltBook Registration")
    print("=" * 70)
    print()

    # Check if already registered
    existing_jwt = os.getenv("MOLTBOOK_JWT", "")
    if existing_jwt:
        print(f"MOLTBOOK_JWT already set: {existing_jwt[:20]}...")
        if check_claim_status(existing_jwt):
            print("Agent is already verified and active!")
            return
        print("Agent registered but not yet verified. Continuing...")
        api_key = existing_jwt
    else:
        # Register
        data = register_agent()
        api_key = print_tweet_instructions(data)

    # Wait for verification
    answer = input("Press Enter after posting the tweet (or 'skip' to exit): ")
    if answer.strip().lower() == "skip":
        print(f"\nYour API key: {api_key}")
        print("Save it and complete verification later.")
        return

    wait_for_verification(api_key)


if __name__ == "__main__":
    main()
