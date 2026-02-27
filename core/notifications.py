import os
import requests
import logging

logger = logging.getLogger(__name__)

def send_telegram_alert(message: str):
    """
    Send a push notification to the verified Telegram user.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_ids = os.getenv("TELEGRAM_CHAT_ID", "").split(",")
    
    if not token or not chat_ids:
        logger.warning("Telegram credentials missing. Cannot send alert.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    for chat_id in chat_ids:
        if not chat_id.strip(): continue
        try:
            payload = {
                "chat_id": chat_id.strip(),
                "text": message,
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
