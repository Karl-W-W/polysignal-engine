#!/usr/bin/env python3
"""
lab/approval_gate.py
====================
Telegram HITL (Human-In-The-Loop) approval gate for PolySignal-OS live trading.

Flow:
  prediction passes risk_gate
    → approval_gate sends trade proposal to Karl via Telegram
    → Karl replies YES or NO (case-insensitive)
    → 5-minute timeout defaults to REJECT (safe)
    → returns ApprovalResult(approved=True/False, reason=...)

Wire into masterloop.py's wait_approval_node() instead of auto-approve stub.

Session 37: Initial implementation
"""

import hashlib
import hmac as _hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").split(",")[0].strip()  # Primary only
HMAC_SECRET        = os.getenv("HMAC_SECRET", "").encode() if os.getenv("HMAC_SECRET") else b""

APPROVAL_TIMEOUT_SECONDS = int(os.getenv("APPROVAL_TIMEOUT_SECONDS", "300"))   # 5 min
POLL_INTERVAL_SECONDS    = float(os.getenv("APPROVAL_POLL_INTERVAL", "3.0"))   # Check every 3s
MAX_POLL_ATTEMPTS        = int(APPROVAL_TIMEOUT_SECONDS / POLL_INTERVAL_SECONDS)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ── Data Model ───────────────────────────────────────────────────────────────

@dataclass
class ApprovalResult:
    approved: bool
    reason: str          # "approved_by_human" | "rejected_by_human" | "timeout" | "error"
    responded_in_seconds: Optional[float] = None


@dataclass
class TradeProposal:
    """Minimal trade proposal for approval display."""
    market_id: str
    title: str
    side: str            # BUY | SELL
    outcome: str         # Yes | No
    size_usdc: float
    price: float
    confidence: float
    risk_score: Optional[float] = None
    signal_source: Optional[str] = None


# ── Telegram helpers ─────────────────────────────────────────────────────────

def _send_message(text: str, parse_mode: str = "Markdown") -> Optional[int]:
    """Send message to primary chat_id. Returns message_id or None."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram credentials not configured")
        return None
    try:
        resp = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            return data["result"]["message_id"]
        logger.error(f"Telegram sendMessage failed: {data}")
        return None
    except Exception as e:
        logger.error(f"Telegram sendMessage error: {e}")
        return None


def _get_updates(offset: int = 0) -> list:
    """Poll Telegram for new messages."""
    try:
        resp = requests.get(
            f"{TELEGRAM_API}/getUpdates",
            params={"offset": offset, "timeout": 2, "allowed_updates": ["message"]},
            timeout=8,
        )
        data = resp.json()
        return data.get("result", []) if data.get("ok") else []
    except Exception as e:
        logger.debug(f"getUpdates error: {e}")
        return []


def _get_latest_update_id() -> int:
    """Get the current highest update_id to use as baseline (ignore old messages)."""
    updates = _get_updates(offset=-1)  # Get only the last update
    if updates:
        return updates[-1]["update_id"]
    return 0


# ── Core gate logic ──────────────────────────────────────────────────────────

def format_proposal_message(proposal: TradeProposal) -> str:
    """Format a human-readable trade proposal for Telegram."""
    emoji = "📈" if proposal.side == "BUY" else "📉"
    direction = f"{'BUY YES' if proposal.side == 'BUY' else 'SELL NO'}"

    lines = [
        f"🔔 *TRADE APPROVAL REQUIRED*",
        f"",
        f"{emoji} *{direction}* — {proposal.title[:80]}",
        f"",
        f"  Market ID: `{proposal.market_id}`",
        f"  Price: `{proposal.price:.3f}` ({proposal.price*100:.1f}¢)",
        f"  Size: `${proposal.size_usdc:.2f} USDC`",
        f"  Confidence: `{proposal.confidence:.0%}`",
    ]

    if proposal.risk_score is not None:
        lines.append(f"  Risk score: `{proposal.risk_score:.2f}`")
    if proposal.signal_source:
        lines.append(f"  Signal: `{proposal.signal_source}`")

    lines += [
        f"",
        f"Reply *YES* to approve or *NO* to reject.",
        f"⏱ Timeout in {APPROVAL_TIMEOUT_SECONDS // 60} minutes → auto-REJECT.",
    ]

    return "\n".join(lines)


def request_approval(proposal: TradeProposal) -> ApprovalResult:
    """
    Send trade proposal to Karl via Telegram and wait for YES/NO reply.

    Returns ApprovalResult with approved=True only on explicit YES.
    Any other outcome (NO, timeout, error) → rejected.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Approval gate: Telegram not configured — auto-rejecting for safety")
        return ApprovalResult(approved=False, reason="error_no_telegram_config")

    # Baseline: ignore messages sent before we asked
    baseline_update_id = _get_latest_update_id()
    next_offset = baseline_update_id + 1

    # Send proposal
    message = format_proposal_message(proposal)
    msg_id = _send_message(message)
    if msg_id is None:
        logger.error("Approval gate: failed to send proposal — auto-rejecting")
        return ApprovalResult(approved=False, reason="error_send_failed")

    logger.info(f"Approval gate: proposal sent (msg_id={msg_id}), waiting up to {APPROVAL_TIMEOUT_SECONDS}s")
    start_time = time.time()

    # Poll for reply
    for attempt in range(MAX_POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed = time.time() - start_time

        if elapsed >= APPROVAL_TIMEOUT_SECONDS:
            break

        updates = _get_updates(offset=next_offset)
        for update in updates:
            next_offset = update["update_id"] + 1
            msg = update.get("message", {})

            # Only accept messages from the authorized chat
            from_chat = str(msg.get("chat", {}).get("id", ""))
            from_user = str(msg.get("from", {}).get("id", ""))
            text = msg.get("text", "").strip().upper()

            if from_chat != TELEGRAM_CHAT_ID and from_user != TELEGRAM_CHAT_ID:
                continue  # Not from Karl's chat

            if text in ("YES", "Y", "APPROVE", "OK", "✅"):
                elapsed = time.time() - start_time
                _send_message(f"✅ *Trade APPROVED* — executing now. (responded in {elapsed:.0f}s)")
                logger.info(f"Approval gate: APPROVED by human in {elapsed:.0f}s")
                return ApprovalResult(
                    approved=True,
                    reason="approved_by_human",
                    responded_in_seconds=elapsed,
                )

            if text in ("NO", "N", "REJECT", "CANCEL", "❌"):
                elapsed = time.time() - start_time
                _send_message(f"❌ *Trade REJECTED* by human.")
                logger.info(f"Approval gate: REJECTED by human in {elapsed:.0f}s")
                return ApprovalResult(
                    approved=False,
                    reason="rejected_by_human",
                    responded_in_seconds=elapsed,
                )

            # Unrecognized reply — inform and keep waiting
            _send_message(
                f"⚠️ Reply not recognized: `{text[:20]}`\n"
                f"Please reply *YES* or *NO*. "
                f"{int(APPROVAL_TIMEOUT_SECONDS - elapsed)}s remaining."
            )

    # Timeout
    _send_message(
        f"⏱ *Approval timeout* — trade REJECTED (no response in "
        f"{APPROVAL_TIMEOUT_SECONDS // 60} minutes)."
    )
    logger.info("Approval gate: TIMEOUT — auto-rejected")
    return ApprovalResult(
        approved=False,
        reason="timeout",
        responded_in_seconds=APPROVAL_TIMEOUT_SECONDS,
    )


def sign_approved_trade(draft: dict) -> Optional[str]:
    """
    Generate HMAC-SHA256 signature for an approved trade draft.
    Same signing logic as masterloop.py commit_node.
    Returns hex signature or None if HMAC_SECRET not configured.
    """
    if not HMAC_SECRET:
        logger.warning("HMAC_SECRET not configured — cannot sign trade")
        return None
    canonical = json.dumps(draft, sort_keys=True, separators=(",", ":")).encode()
    return _hmac.new(HMAC_SECRET, canonical, hashlib.sha256).hexdigest()


# ── Drop-in replacement for wait_approval_node stub ─────────────────────────

def wait_approval_node_with_hitl(state: dict) -> dict:
    """
    Drop-in replacement for the auto-approve stub in masterloop.py.

    Usage in masterloop.py:
        # Replace:
        from lab.approval_gate import wait_approval_node_with_hitl
        # In graph definition, swap wait_approval_node → wait_approval_node_with_hitl
        # Or monkey-patch:
        # import workflows.masterloop as ml
        # ml.wait_approval_node = wait_approval_node_with_hitl
    """
    draft = state.get("draft_action", {})

    # Build proposal from state
    proposal = TradeProposal(
        market_id=draft.get("market_id", "unknown"),
        title=draft.get("title", "Unknown Market"),
        side=draft.get("side", "?"),
        outcome=draft.get("outcome", "?"),
        size_usdc=draft.get("size_usdc", 0.0),
        price=draft.get("price", 0.0),
        confidence=state.get("confidence", 0.0),
        risk_score=state.get("risk_score"),
        signal_source=state.get("signal_source"),
    )

    result = request_approval(proposal)

    state["human_approved"] = result.approved
    state["approval_reason"] = result.reason
    state["approval_latency_s"] = result.responded_in_seconds

    if result.approved:
        sig = sign_approved_trade(draft)
        if sig:
            state["signature"] = sig
            logger.info("Trade signed and ready for commit_node")
        else:
            state["human_approved"] = False
            state["approval_reason"] = "error_no_hmac_secret"
            logger.error("Approved but cannot sign — HMAC_SECRET missing")
    else:
        logger.info(f"Trade not approved: {result.reason}")

    return state


# ── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Quick smoke test: send a fake proposal and wait for response
    print("=== Approval Gate Smoke Test ===")
    print(f"Bot token configured: {'YES' if TELEGRAM_BOT_TOKEN else 'NO'}")
    print(f"Chat ID: {TELEGRAM_CHAT_ID or 'NOT SET'}")
    print(f"Timeout: {APPROVAL_TIMEOUT_SECONDS}s")
    print()

    test_proposal = TradeProposal(
        market_id="TEST-001",
        title="Will this approval gate work? — Test",
        side="BUY",
        outcome="Yes",
        size_usdc=1.00,
        price=0.42,
        confidence=0.87,
        risk_score=0.31,
        signal_source="approval_gate_test",
    )

    print("Sending test proposal to Telegram...")
    result = request_approval(test_proposal)
    print(f"\nResult: approved={result.approved}, reason={result.reason}, "
          f"latency={result.responded_in_seconds:.0f}s" if result.responded_in_seconds else
          f"\nResult: approved={result.approved}, reason={result.reason}")
    sys.exit(0 if result.approved else 1)
