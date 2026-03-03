import os
import hashlib
import time
import requests
import logging

logger = logging.getLogger(__name__)

# ── Notification dedup ───────────────────────────────────────────────────────
# Prevents spamming Telegram with identical messages every scanner cycle.
# Same message won't be re-sent within COOLDOWN_SECONDS.
COOLDOWN_SECONDS = int(os.getenv("TELEGRAM_COOLDOWN_SECONDS", "3600"))  # 1 hour
_recent_alerts: dict[str, float] = {}  # message_hash → timestamp


def send_telegram_alert(message: str):
    """
    Send a push notification to the verified Telegram user.
    Deduplicates: same message won't be re-sent within COOLDOWN_SECONDS.
    """
    # Dedup check
    msg_hash = hashlib.md5(message.encode()).hexdigest()[:12]
    now = time.time()
    last_sent = _recent_alerts.get(msg_hash, 0)
    if now - last_sent < COOLDOWN_SECONDS:
        logger.debug(f"Telegram alert suppressed (cooldown): {message[:60]}...")
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_ids = os.getenv("TELEGRAM_CHAT_ID", "").split(",")

    if not token or not chat_ids:
        logger.warning("Telegram credentials missing. Cannot send alert.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    sent = False
    for chat_id in chat_ids:
        if not chat_id.strip(): continue
        try:
            payload = {
                "chat_id": chat_id.strip(),
                "text": message,
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=5)
            sent = True
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

    if sent:
        _recent_alerts[msg_hash] = now
        # Prune old entries (keep cache small)
        cutoff = now - COOLDOWN_SECONDS * 2
        expired = [k for k, v in _recent_alerts.items() if v < cutoff]
        for k in expired:
            del _recent_alerts[k]
