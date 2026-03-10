#!/usr/bin/env python3
"""
lab/moltbook_math_solver.py
=============================
MoltBook Math Verification Challenge Solver.

MoltBook requires new agents to solve obfuscated arithmetic challenges
before posting. This module handles the challenge flow:
1. Detect when a 403/challenge response is received
2. Parse the math expression from the challenge
3. Solve it (to 2 decimal places)
4. Submit the answer to /verify

Usage:
    from lab.moltbook_math_solver import solve_verification_challenge

    # If a post attempt returns a challenge:
    success = solve_verification_challenge(config)

Integration with publisher:
    The publisher calls this automatically when it receives a verification
    challenge response, then retries the post.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

MOLTBOOK_API = "https://www.moltbook.com/api/v1"


def parse_math_challenge(challenge_text: str) -> Optional[str]:
    """Extract the math expression from a MoltBook verification challenge.

    MoltBook challenges are obfuscated but contain standard arithmetic:
    - Basic operations: +, -, *, /
    - Parentheses
    - Decimal numbers
    - Sometimes word-based ("What is 42 plus 17?")

    Returns the expression string, or None if unparseable.
    """
    # Pattern 1: Direct expression (e.g., "Solve: 42.5 + 17.3 * 2")
    expr_match = re.search(
        r"(?:solve|calculate|compute|answer|what is)[:\s]*"
        r"([\d\s\.\+\-\*/\(\)]+)",
        challenge_text,
        re.IGNORECASE,
    )
    if expr_match:
        return expr_match.group(1).strip()

    # Pattern 2: Word-based arithmetic ("What is forty-two plus seventeen?")
    word_numbers = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
        "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90, "hundred": 100,
    }
    word_ops = {
        "plus": "+", "minus": "-", "times": "*", "multiplied by": "*",
        "divided by": "/", "over": "/",
    }

    text = challenge_text.lower()
    # Replace word operators first
    for word, op in word_ops.items():
        text = text.replace(word, f" {op} ")

    # Replace word numbers
    for word, num in sorted(word_numbers.items(), key=lambda x: -len(x[0])):
        text = text.replace(word, str(num))

    # Try to extract a numeric expression
    expr_match = re.search(r"([\d\s\.\+\-\*/\(\)]+)", text)
    if expr_match:
        expr = expr_match.group(1).strip()
        if any(op in expr for op in "+-*/"):
            return expr

    # Pattern 3: Just a bare expression in the response
    bare_match = re.search(r"(\d+\.?\d*\s*[\+\-\*/]\s*\d+\.?\d*(?:\s*[\+\-\*/]\s*\d+\.?\d*)*)", challenge_text)
    if bare_match:
        return bare_match.group(1).strip()

    return None


def solve_expression(expr: str) -> Optional[float]:
    """Safely evaluate a math expression.

    Only allows: digits, decimal points, +, -, *, /, (, ), whitespace.
    Returns result rounded to 2 decimal places.
    """
    # Security: only allow safe characters
    if not re.match(r'^[\d\s\.\+\-\*/\(\)]+$', expr):
        logger.warning("Unsafe expression rejected: %s", expr[:100])
        return None

    try:
        # Use eval with empty namespace — safe because we validated the input
        result = eval(expr, {"__builtins__": {}}, {})
        return round(float(result), 2)
    except Exception as e:
        logger.warning("Failed to evaluate '%s': %s", expr, e)
        return None


def solve_verification_challenge(
    jwt: str,
    api_base: str = MOLTBOOK_API,
    challenge_data: dict = None,
) -> Tuple[bool, str]:
    """Solve a MoltBook math verification challenge.

    Args:
        jwt: MoltBook API key
        api_base: API base URL
        challenge_data: Optional pre-fetched challenge data.
                       If None, fetches a new challenge.

    Returns:
        (success: bool, message: str)
    """
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }

    # If no challenge data provided, trigger one by checking verification status
    if not challenge_data:
        try:
            resp = requests.get(
                f"{api_base}/verify",
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                return True, "Already verified"
            challenge_data = resp.json()
        except requests.RequestException as e:
            return False, f"Failed to fetch challenge: {e}"

    # Extract the challenge text
    challenge_text = (
        challenge_data.get("challenge", "") or
        challenge_data.get("question", "") or
        challenge_data.get("message", "") or
        str(challenge_data)
    )

    if not challenge_text:
        return False, "No challenge text found in response"

    logger.info("Challenge: %s", challenge_text[:200])

    # Parse and solve
    expr = parse_math_challenge(challenge_text)
    if not expr:
        return False, f"Could not parse expression from: {challenge_text[:200]}"

    answer = solve_expression(expr)
    if answer is None:
        return False, f"Could not evaluate expression: {expr}"

    # Format answer to 2 decimal places (MoltBook requirement)
    answer_str = f"{answer:.2f}"
    logger.info("Solving: %s = %s", expr, answer_str)

    # Submit answer
    try:
        resp = requests.post(
            f"{api_base}/verify",
            headers=headers,
            json={"answer": answer_str},
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("success") or result.get("verified"):
            return True, f"Verified! Answer: {answer_str}"
        else:
            return False, f"Wrong answer ({answer_str}): {result}"

    except requests.RequestException as e:
        return False, f"Verification submission failed: {e}"


def ensure_verified(jwt: str, api_base: str = MOLTBOOK_API, max_attempts: int = 3) -> bool:
    """Ensure the agent is verified. Retries up to max_attempts.

    Returns True if verified (or already verified), False if all attempts fail.
    """
    for attempt in range(max_attempts):
        success, message = solve_verification_challenge(jwt, api_base)
        logger.info("Verification attempt %d: %s — %s", attempt + 1, success, message)

        if success:
            return True

        time.sleep(2)  # Brief pause before retry

    return False


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    jwt = os.getenv("MOLTBOOK_JWT", "")
    if not jwt:
        print("Set MOLTBOOK_JWT to test")
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "test-parse":
        # Test the parser with sample challenges
        tests = [
            "Solve: 42.5 + 17.3",
            "What is 100 divided by 3?",
            "Calculate: (25 + 15) * 2",
            "Compute: 3.14 * 2.0 - 1.28",
            "What is twenty plus thirty-five?",
        ]
        for t in tests:
            expr = parse_math_challenge(t)
            answer = solve_expression(expr) if expr else None
            print(f"  '{t}' → expr='{expr}' → answer={answer}")
    else:
        success = ensure_verified(jwt)
        print(f"Verification: {'SUCCESS' if success else 'FAILED'}")
