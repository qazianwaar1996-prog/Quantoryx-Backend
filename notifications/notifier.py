# notifications/notifier.py
"""
Quantoryx — Asynchronous Notification Delivery Dispatcher.

Coordinates alert broadcasts to Telegram, Discord, Email, and live WebSockets.
Utilizes standard non-blocking HTTP and SMTP client pools [9].
"""

import os
import sys
import asyncio
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

# Ensure project root is in search path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.logging_config import get_logger
from backend.api.ws_endpoints import manager as ws_manager

logger = get_logger("notifications.dispatcher")

# Defensive imports [4]
try:
    import aiohttp
except ImportError:
    aiohttp = None
    logger.warning("aiohttp library is missing. Install it to enable Telegram and Discord notifications.")


class NotificationDispatcher:
    """
    Asynchronous notification delivery hub [9].
    """

    def __init__(self, smtp_config: Optional[Dict[str, Any]] = None):
        """
        Expected SMTP Config Parameters:
            - host: str (e.g., smtp.mailgun.org)
            - port: int (usually 587 or 465)
            - username: str
            - password: str
            - sender_email: str
        """
        self.smtp_config = smtp_config or {}

    # =====================================================================
    # CHANNEL-SPECIFIC ADAPTER DELIVERIES (Async)
    # =====================================================================

    async def send_telegram(self, bot_token: str, chat_id: str, message: str) -> bool:
        """Dispatches an alert to a target Telegram Chat ID over the Bot API [9]."""
        if aiohttp is None:
            logger.error("Telegram notification cancelled: aiohttp library is unavailable.")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.debug("Telegram alert delivered successfully to Chat ID %s.", chat_id)
                        return True
                    else:
                        resp_text = await response.text()
                        logger.error("Telegram API rejected message (Status %s): %s", response.status, resp_text)
                        return False
        except Exception as e:
            logger.error("Failed to send Telegram alert: %s", str(e))
            return False

    async def send_discord(self, webhook_url: str, message: str) -> bool:
        """Dispatches an alert to a target Discord Webhook URL [9]."""
        if aiohttp is None:
            logger.error("Discord notification cancelled: aiohttp library is unavailable.")
            return False

        payload = {
            "content": message
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status in [200, 204]:
                        logger.debug("Discord alert delivered successfully to webhook channel.")
                        return True
                    else:
                        resp_text = await response.text()
                        logger.error("Discord API rejected message (Status %s): %s", response.status, resp_text)
                        return False
        except Exception as e:
            logger.error("Failed to send Discord alert: %s", str(e))
            return False

    async def send_email(self, recipient_email: str, subject: str, body: str) -> bool:
        """Dispatches an alert email using standard SMTP configurations [9]."""
        if not self.smtp_config:
            logger.warning("Email notification skipped: SMTP configuration is not provided.")
            return False

        msg = MIMEText(body, "html")
        msg["Subject"] = subject
        msg["From"] = self.smtp_config.get("sender_email", "alerts@quantoryx.com")
        msg["To"] = recipient_email

        try:
            # Wrap blocking SMTP calls inside an execution thread to prevent ASGI thread pool delays [1, 2]
            def _dispatch():
                host = self.smtp_config.get("host", "localhost")
                port = int(self.smtp_config.get("port", 587))
                user = self.smtp_config.get("username", "")
                password = self.smtp_config.get("password", "")

                with smtplib.SMTP(host, port, timeout=5.0) as server:
                    server.starttls()
                    if user and password:
                        server.login(user, password)
                    server.sendmail(msg["From"], [recipient_email], msg.as_string())

            await asyncio.to_thread(_dispatch)
            logger.debug("Email notification delivered successfully to %s.", recipient_email)
            return True
        except Exception as e:
            logger.error("Failed to deliver Email notification: %s", str(e))
            return False

    async def send_web_push(self, user_id: str, title: str, message: str) -> bool:
        """
        Delivers an in-app Web Push alert instantly using our active WebSocket manager [9].
        """
        payload = {
            "type": "NOTIFICATION",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "title": title,
                "message": message
            }
        }
        await ws_manager.send_to_user(user_id=user_id, message=payload)
        logger.debug("Web Push notification delivered via WebSockets to User %s.", user_id)
        return True

    # =====================================================================
    # UNIFIED BROADCAST GATEWAY
    # =====================================================================

    async def broadcast_alert(
        self,
        user_id: str,
        alert_type: str,
        title: str,
        message: str,
        delivery_config: Dict[str, Any]
    ):
        """
        Formats alert payloads and dispatches them across all user-enabled channels [9].
        
        Parameters:
            user_id: Recipient User UUID
            alert_type: Type of event ("TRADE_OPENED", "MARGIN_ALERT", "BROKER_DISCONNECT", etc.)
            title: Headline summary
            message: Alert body
            delivery_config: Dict containing user-specific channel configs:
                {
                    "web_push": true,
                    "telegram": {"enabled": true, "bot_token": "...", "chat_id": "..."},
                    "discord": {"enabled": true, "webhook_url": "..."},
                    "email": {"enabled": true, "recipient": "..."}
                }
        """
        formatted_message = f"<b>[{alert_type}] {title}</b>\n\n{message}\n\n<i>Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
        tasks = []

        # 1. In-App Web Push (WebSocket Channel)
        if delivery_config.get("web_push", True):
            tasks.append(self.send_web_push(user_id, title, message))

        # 2. Telegram Alert
        tg_cfg = delivery_config.get("telegram", {})
        if tg_cfg.get("enabled") and tg_cfg.get("bot_token") and tg_cfg.get("chat_id"):
            tasks.append(self.send_telegram(tg_cfg["bot_token"], tg_cfg["chat_id"], formatted_message))

        # 3. Discord Alert
        ds_cfg = delivery_config.get("discord", {})
        if ds_cfg.get("enabled") and ds_cfg.get("webhook_url"):
            # Discord markup uses simple markdown instead of HTML
            discord_message = f"**[{alert_type}] {title}**\n\n{message}\n\n*Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC*"
            tasks.append(self.send_discord(ds_cfg["webhook_url"], discord_message))

        # 4. Email Alert
        em_cfg = delivery_config.get("email", {})
        if em_cfg.get("enabled") and em_cfg.get("recipient"):
            html_email_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; color: #333333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #dddddd; border-radius: 5px;">
                        <h2 style="color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 10px;">[{alert_type}] {title}</h2>
                        <p style="font-size: 16px; line-height: 1.5;">{message}</p>
                        <p style="font-size: 12px; color: #777777; border-top: 1px solid #dddddd; padding-top: 10px; margin-top: 20px;">
                            This is an automated alert generated by the Quantoryx research system. Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                        </p>
                    </div>
                </body>
            </html>
            """
            tasks.append(self.send_email(em_cfg["recipient"], f"[{config.SYSTEM_NAME} Alert] {title}", html_email_body))

        # Dispatch all notifications concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
