"""Dashboard page for Telegram Bot & Firebase Push Notifications - Real integration."""

import os
import streamlit as st
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="User Notifications", page_icon=":robot_face:", layout="wide")
st.title(":robot_face: User Notifications")
st.markdown("Telegram Bot alerts & Firebase push notifications for drivers and authorities.")
st.markdown("---")

# ─── Main Content ────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Telegram Bot", "Firebase Push", "Configuration"])

with tab1:
    st.subheader("Telegram Traffic Alert Bot")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### How It Works")
        st.markdown("""
        1. **Create Bot**: Talk to [@BotFather](https://t.me/BotFather) on Telegram -> `/newbot` -> get token
        2. **Set Token**: Enter token below or add `TELEGRAM_BOT_TOKEN=your_token` in `.env` file
        3. **Users Subscribe**: Users open your bot and send `/start`
        4. **Auto Alerts**: System sends traffic/accident/emergency alerts automatically

        ### Bot Commands

        | Command | Description |
        |---------|-------------|
        | `/start` | Register for traffic alerts |
        | `/stop` | Unsubscribe from all alerts |
        | `/subscribe cam_01` | Subscribe to a specific camera |
        | `/unsubscribe cam_01` | Unsubscribe from a camera |
        | `/status` | Get current traffic at all cameras |
        | `/help` | Show all commands |
        """)

    with col2:
        st.markdown("### Bot Status")

        # Check for token
        bot_token = st.text_input("Bot Token", type="password", key="tg_token",
                                   value=os.getenv("TELEGRAM_BOT_TOKEN", ""))

        # Check subscriber count
        sub_file = Path("data/telegram_subscribers.json")
        subscriber_count = 0
        subscribers = []
        if sub_file.exists():
            try:
                with open(sub_file, "r") as f:
                    subscribers = json.load(f)
                    subscriber_count = len(subscribers)
            except (json.JSONDecodeError, IOError):
                pass

        st.metric("Subscribers", subscriber_count)

        # Try to verify bot token
        if bot_token:
            try:
                import requests as req
                resp = req.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
                if resp.ok:
                    bot_info = resp.json().get("result", {})
                    st.success(f"Bot connected: @{bot_info.get('username', 'N/A')}")
                    st.metric("Bot Status", "Connected")
                else:
                    st.warning("Invalid bot token.")
                    st.metric("Bot Status", "Invalid Token")
            except Exception as e:
                st.warning(f"Bot verification error: {e}")
                st.metric("Bot Status", "Error")

            if st.button("Send Test Message to Subscribers"):
                if subscribers:
                    try:
                        from src.telegram_bot.bot import TrafficAlertBot

                        bot = TrafficAlertBot(token=bot_token)
                        final_counts = st.session_state.get("final_counts", {})
                        message = "Test alert from Traffic Management System\n"
                        if final_counts:
                            message += f"Current vehicle count: {final_counts.get('total', 0)}"
                        else:
                            message += "System is running."

                        sent = 0
                        for sub in subscribers:
                            chat_id = sub.get("chat_id", sub) if isinstance(sub, dict) else sub
                            if bot.send_message(int(chat_id), message):
                                sent += 1
                        st.success(f"Message sent to {sent} subscriber(s)!")
                    except Exception as e:
                        st.error(f"Send error: {e}")
                else:
                    st.warning("No subscribers yet. Users need to `/start` the bot first.")
        else:
            st.metric("Bot Status", "No Token")
            st.info("Enter bot token or set `TELEGRAM_BOT_TOKEN` in `.env`")

        st.markdown("---")
        st.markdown("### Alert Types Sent")
        st.markdown("""
        - :red_circle: **Accidents** -> All subscribers
        - :orange_circle: **Illegal vehicles** -> Authority subscribers
        - :large_yellow_circle: **Heavy traffic** -> Route subscribers
        - :ambulance: **Emergency** -> All subscribers
        """)

    # Show subscribers
    if subscribers:
        st.markdown("---")
        st.markdown("### Active Subscribers")
        import pandas as pd
        sub_data = []
        for sub in subscribers:
            if isinstance(sub, dict):
                sub_data.append({
                    "Chat ID": sub.get("chat_id", "N/A"),
                    "Name": sub.get("name", "N/A"),
                    "Subscribed Cameras": ", ".join(sub.get("cameras", ["all"])),
                    "Priority": sub.get("min_priority", "MEDIUM"),
                })
            else:
                sub_data.append({"Chat ID": sub})
        if sub_data:
            st.dataframe(pd.DataFrame(sub_data), use_container_width=True)

with tab2:
    st.subheader("Firebase Cloud Messaging (FCM)")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### Setup Guide")
        st.markdown("""
        1. Go to [Firebase Console](https://console.firebase.google.com)
        2. Create project -> Enable Cloud Messaging
        3. Download service account key JSON
        4. Set `FIREBASE_CREDENTIALS_PATH=path/to/key.json` in `.env`
        """)

        st.markdown("### Notification Topics")
        st.markdown("""
        | Topic | Subscribers Get |
        |-------|----------------|
        | `traffic_alerts` | Heavy traffic & signal changes |
        | `accident_alerts` | Collision & sudden stop events |
        | `emergency_alerts` | Ambulance/fire truck detection |
        | `security_alerts` | Illegal vehicle detections |
        """)

    with col2:
        st.markdown("### FCM Status")

        token_file = Path("data/fcm_device_tokens.json")
        device_count = 0
        if token_file.exists():
            try:
                with open(token_file, "r") as f:
                    tokens = json.load(f)
                    device_count = len(tokens)
            except (json.JSONDecodeError, IOError):
                pass

        st.metric("Registered Devices", device_count)

        cred_path = st.text_input("Credentials JSON Path",
                                   value=os.getenv("FIREBASE_CREDENTIALS_PATH", ""),
                                   placeholder="path/to/firebase-key.json")

        if st.button("Test FCM Connection"):
            if cred_path and Path(cred_path).exists():
                try:
                    from src.firebase_notifications.fcm_sender import FCMSender
                    fcm = FCMSender(credentials_path=cred_path)
                    st.success("Firebase connected successfully!")
                    st.metric("FCM Status", "Connected")
                except Exception as e:
                    st.error(f"Firebase error: {e}")
            elif cred_path:
                st.error(f"Credentials file not found: {cred_path}")
            else:
                st.warning("Set credentials path first.")

with tab3:
    st.subheader("Notification Configuration")

    st.markdown("### Environment Variables (.env)")
    st.code("""
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Firebase Cloud Messaging
FIREBASE_CREDENTIALS_PATH=path/to/firebase-adminsdk-key.json
FIREBASE_PROJECT_ID=your-project-id

# OpenRouteService (for route suggestions)
ORS_API_KEY=your_openrouteservice_api_key

# Twilio SMS
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1234567890
    """, language="bash")

    st.markdown("### Alert Priority Routing")

    priority_config = {
        "CRITICAL": {"sms": True, "telegram": True, "fcm": True, "dashboard": True},
        "HIGH": {"sms": True, "telegram": True, "fcm": True, "dashboard": True},
        "MEDIUM": {"sms": False, "telegram": True, "fcm": True, "dashboard": True},
        "LOW": {"sms": False, "telegram": False, "fcm": False, "dashboard": True},
    }

    for priority, channels in priority_config.items():
        with st.expander(f"{priority} Priority"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.checkbox("SMS", value=channels["sms"], key=f"p_sms_{priority}")
            with c2:
                st.checkbox("Telegram", value=channels["telegram"], key=f"p_tg_{priority}")
            with c3:
                st.checkbox("Firebase", value=channels["fcm"], key=f"p_fcm_{priority}")
            with c4:
                st.checkbox("Dashboard", value=channels["dashboard"], key=f"p_dash_{priority}", disabled=True)
