"""Telegram Bot for real-time traffic alerts to users.

Users can:
- Subscribe to specific camera/route alerts
- Get notified about heavy traffic, accidents, emergencies
- Query current traffic status at any camera

Setup:
1. Create bot via @BotFather on Telegram
2. Get bot token
3. Set TELEGRAM_BOT_TOKEN in .env
"""

import os
import json
import time
import threading
from typing import Dict, List, Optional, Set
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

import requests


@dataclass
class Subscriber:
    """A Telegram user subscribed to alerts."""
    chat_id: int
    username: str = ""
    subscribed_cameras: List[str] = field(default_factory=list)
    min_priority: str = "MEDIUM"
    is_active: bool = True


class TrafficAlertBot:
    """Telegram bot that sends traffic alerts to subscribed users.

    Commands:
        /start - Register for alerts
        /subscribe <camera_id> - Subscribe to a camera's alerts
        /unsubscribe <camera_id> - Unsubscribe from a camera
        /status - Get current traffic status at all cameras
        /status <camera_id> - Get traffic at a specific camera
        /help - Show available commands
    """

    TELEGRAM_API = "https://api.telegram.org/bot{token}"

    def __init__(
        self,
        token: Optional[str] = None,
        subscribers_file: Optional[str] = None,
    ):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._subscribers: Dict[int, Subscriber] = {}
        self._camera_status: Dict[str, Dict] = {}
        self._running = False
        self._last_update_id = 0

        self._subscribers_file = Path(
            subscribers_file or "data/telegram_subscribers.json"
        )
        self._load_subscribers()

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    @property
    def api_url(self) -> str:
        return self.TELEGRAM_API.format(token=self.token)

    # ─── Sending Messages ───────────────────────────────────────────────

    def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
        """Send a text message to a Telegram user."""
        if not self.is_configured:
            logger.warning("Telegram bot not configured. Skipping message.")
            return False

        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
                timeout=10,
            )
            return response.ok
        except requests.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def broadcast_alert(self, alert) -> int:
        """Send an alert to all relevant subscribers.

        Args:
            alert: An Alert object from the alert system.

        Returns:
            Number of messages sent successfully.
        """
        priority_levels = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        sent_count = 0

        emoji_map = {
            "accident": "🚨",
            "heavy_traffic": "🚗",
            "illegal_vehicle": "🚔",
            "emergency_vehicle": "🚑",
            "signal_override": "🚦",
        }

        emoji = emoji_map.get(alert.alert_type.value, "⚠️")
        message = (
            f"{emoji} <b>{alert.title}</b>\n\n"
            f"📋 {alert.message}\n"
            f"📍 Location: {alert.location or 'N/A'}\n"
            f"📹 Camera: {alert.camera_id or 'N/A'}\n"
            f"⚡ Priority: {alert.priority.name}\n"
            f"🕐 Time: {time.strftime('%H:%M:%S', time.localtime(alert.timestamp))}"
        )

        alert_priority_value = priority_levels.get(alert.priority.name, 2)

        for subscriber in self._subscribers.values():
            if not subscriber.is_active:
                continue

            sub_priority_value = priority_levels.get(subscriber.min_priority, 2)
            if alert_priority_value < sub_priority_value:
                continue

            # Check if subscriber is interested in this camera
            if subscriber.subscribed_cameras and alert.camera_id:
                if alert.camera_id not in subscriber.subscribed_cameras:
                    continue

            if self.send_message(subscriber.chat_id, message):
                sent_count += 1

        return sent_count

    def send_traffic_status(self, chat_id: int, camera_id: Optional[str] = None):
        """Send current traffic status to a user."""
        if camera_id and camera_id in self._camera_status:
            cam = self._camera_status[camera_id]
            message = (
                f"📹 <b>{cam.get('name', camera_id)}</b>\n"
                f"🚗 Vehicles: {cam.get('count', 0)}\n"
                f"🚦 Density: {cam.get('density', 'unknown').upper()}\n"
                f"🕐 Updated: {cam.get('updated', 'N/A')}"
            )
        elif self._camera_status:
            lines = ["📊 <b>Traffic Status - All Cameras</b>\n"]
            for cid, cam in self._camera_status.items():
                density = cam.get("density", "unknown")
                emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "congested": "🔴"}.get(density, "⚪")
                lines.append(
                    f"{emoji} <b>{cam.get('name', cid)}</b>: "
                    f"{cam.get('count', 0)} vehicles ({density.upper()})"
                )
            message = "\n".join(lines)
        else:
            message = "No traffic data available yet."

        self.send_message(chat_id, message)

    # ─── Subscriber Management ──────────────────────────────────────────

    def add_subscriber(self, chat_id: int, username: str = ""):
        """Register a new subscriber."""
        if chat_id not in self._subscribers:
            self._subscribers[chat_id] = Subscriber(
                chat_id=chat_id, username=username
            )
            self._save_subscribers()
            self.send_message(
                chat_id,
                "✅ <b>Registered for traffic alerts!</b>\n\n"
                "Commands:\n"
                "/subscribe &lt;camera_id&gt; - Subscribe to a camera\n"
                "/status - Get current traffic\n"
                "/help - All commands",
            )

    def remove_subscriber(self, chat_id: int):
        """Remove a subscriber."""
        self._subscribers.pop(chat_id, None)
        self._save_subscribers()

    def update_camera_status(self, camera_id: str, name: str, count: int, density: str):
        """Update traffic status for a camera (called by pipeline)."""
        self._camera_status[camera_id] = {
            "name": name,
            "count": count,
            "density": density,
            "updated": time.strftime("%H:%M:%S"),
        }

    # ─── Polling for Commands ───────────────────────────────────────────

    def process_updates(self):
        """Poll for and process incoming Telegram messages (bot commands)."""
        if not self.is_configured:
            return

        try:
            response = requests.get(
                f"{self.api_url}/getUpdates",
                params={"offset": self._last_update_id + 1, "timeout": 5},
                timeout=15,
            )
            if not response.ok:
                return

            updates = response.json().get("result", [])
            for update in updates:
                self._last_update_id = update["update_id"]
                message = update.get("message", {})
                text = message.get("text", "")
                chat_id = message.get("chat", {}).get("id")
                username = message.get("from", {}).get("username", "")

                if not chat_id or not text:
                    continue

                self._handle_command(chat_id, username, text)

        except requests.RequestException:
            pass

    def _handle_command(self, chat_id: int, username: str, text: str):
        """Handle incoming bot commands."""
        parts = text.strip().split()
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        if command == "/start":
            self.add_subscriber(chat_id, username)

        elif command == "/stop":
            self.remove_subscriber(chat_id)
            self.send_message(chat_id, "🔕 Unsubscribed from all alerts.")

        elif command == "/subscribe" and args:
            cam_id = args[0]
            if chat_id in self._subscribers:
                if cam_id not in self._subscribers[chat_id].subscribed_cameras:
                    self._subscribers[chat_id].subscribed_cameras.append(cam_id)
                    self._save_subscribers()
                self.send_message(chat_id, f"✅ Subscribed to camera: {cam_id}")

        elif command == "/unsubscribe" and args:
            cam_id = args[0]
            if chat_id in self._subscribers:
                self._subscribers[chat_id].subscribed_cameras = [
                    c for c in self._subscribers[chat_id].subscribed_cameras if c != cam_id
                ]
                self._save_subscribers()
                self.send_message(chat_id, f"🔕 Unsubscribed from camera: {cam_id}")

        elif command == "/status":
            cam_id = args[0] if args else None
            self.send_traffic_status(chat_id, cam_id)

        elif command == "/help":
            self.send_message(
                chat_id,
                "🤖 <b>Traffic Alert Bot - Commands</b>\n\n"
                "/start - Register for alerts\n"
                "/stop - Unsubscribe from all alerts\n"
                "/subscribe &lt;camera_id&gt; - Subscribe to camera\n"
                "/unsubscribe &lt;camera_id&gt; - Unsubscribe from camera\n"
                "/status - All cameras traffic status\n"
                "/status &lt;camera_id&gt; - Specific camera status\n"
                "/help - Show this help",
            )

    def start_polling(self):
        """Start background thread to poll for commands."""
        if not self.is_configured:
            logger.warning("Telegram bot token not set. Polling disabled.")
            return

        self._running = True

        def _poll_loop():
            while self._running:
                self.process_updates()
                time.sleep(2)

        thread = threading.Thread(target=_poll_loop, daemon=True)
        thread.start()
        logger.info("Telegram bot polling started.")

    def stop_polling(self):
        self._running = False

    # ─── Persistence ────────────────────────────────────────────────────

    def _save_subscribers(self):
        try:
            self._subscribers_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                str(cid): {
                    "chat_id": s.chat_id,
                    "username": s.username,
                    "subscribed_cameras": s.subscribed_cameras,
                    "min_priority": s.min_priority,
                    "is_active": s.is_active,
                }
                for cid, s in self._subscribers.items()
            }
            with open(self._subscribers_file, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save subscribers: {e}")

    def _load_subscribers(self):
        if self._subscribers_file.exists():
            try:
                with open(self._subscribers_file, "r") as f:
                    data = json.load(f)
                for cid_str, info in data.items():
                    cid = int(cid_str)
                    self._subscribers[cid] = Subscriber(
                        chat_id=info["chat_id"],
                        username=info.get("username", ""),
                        subscribed_cameras=info.get("subscribed_cameras", []),
                        min_priority=info.get("min_priority", "MEDIUM"),
                        is_active=info.get("is_active", True),
                    )
            except (json.JSONDecodeError, IOError):
                pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
