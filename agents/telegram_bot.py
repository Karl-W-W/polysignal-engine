#!/usr/bin/env python3
"""
telegram_bot.py
Bridge between Telegram and the MasterLoop OS.
Handles routing between System Controller (Port 5000) and Agent Brain (Port 8000).
"""

import os
import logging
import json
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Load environment
from dotenv import load_dotenv
load_dotenv("/opt/loop/.env")

# Config
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_IDS = [int(id.strip()) for id in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if id.strip()]

# Dual-Backend Architecture
SYSTEM_URL = "http://backend:5000"   # app.py (Status, State)
AGENT_URL = "http://backend:8000"    # streaming_agent.py (LLM + Tools)

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def check_auth(update: Update) -> bool:
    if update.effective_chat.id not in ALLOWED_CHAT_IDS:
        await update.message.reply_text("⛔ Not Authorized.")
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    await update.message.reply_text(
        "🛡️ **PolySignal OS Online**\n"
        "Direct Neural Link Established.\n\n"
        "• Talk naturally to interact with the Agent.\n"
        "• /status to check system health.",
        parse_mode='Markdown'
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    
    try:
        # Hit Port 5000 for System Status
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{SYSTEM_URL}/api/status", timeout=5.0)
            data = res.json()
            
            # Format nicely
            status_msg = (
                f"📊 **System Status**\n"
                f"• Cycle: #{data.get('cycle_number', '?')}\n"
                f"• State: `{data.get('execution_status', 'UNKNOWN')}`\n"
            )
            
            # Add recent logs if available
            logs = data.get("logs", [])
            if logs:
                status_msg += "\n**Recent Activity:**\n"
                for log in logs[-3:]:
                    icon = "🔹"
                    if log.get("type") == "audit": icon = "👁️"
                    if log.get("type") == "error": icon = "❌"
                    status_msg += f"{icon} {log.get('message')}\n"
            
            await update.message.reply_text(status_msg, parse_mode='Markdown')
            
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to reach System Controller: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return

    user_text = update.message.text
    chat_id = update.effective_chat.id
    
    # Send initial placeholder
    status_msg = await update.message.reply_text("🤔 Thinking...")
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    full_response = ""
    last_update_text = ""
    
    try:
        # Hit Port 8000 for Agent Streaming
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream('POST', f"{AGENT_URL}/api/agent/stream", json={"input": user_text}) as response:
                
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                        
                    data_str = line.removeprefix("data: ")
                    try:
                        chunk = json.loads(data_str)
                    except:
                        continue
                        
                    if chunk["type"] == "chunk":
                        # Content is now clean text from streaming agent
                        content = chunk.get("content", "")
                        if content and content.strip():
                            full_response += content
                        
                        # Update message every ~50 chars to show progress (filtering low-value updates helps API limits)
                        if len(full_response) - len(last_update_text) > 100:
                            try:
                                await context.bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=status_msg.message_id,
                                    text=full_response + " ▌"
                                )
                                last_update_text = full_response
                            except:
                                pass # Ignore edit errors (rate limits)

                    elif chunk["type"] == "error":
                        full_response += f"\n\n❌ ERROR: {chunk.get('message')}"
                    
                    elif chunk["type"] == "done":
                        break

        # Final Update
        if not full_response.strip():
            full_response = "✅ Task Completed (No Output)."
            
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=full_response,
            parse_mode='Markdown'
        )

    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ Brain Connection Failed: {e}"
        )

def run_bot():
    if not TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN found")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    logger.info("Telegram Bot Polling Started...")
    application.run_polling()

if __name__ == '__main__':
    run_bot()
