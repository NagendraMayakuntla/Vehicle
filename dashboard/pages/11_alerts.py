"""Dashboard page for Alert System - Real AlertManager + NotificationSender."""

import json
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="Alert System", page_icon=":bell:", layout="wide")
st.title(":bell: Alert System")
st.markdown("SMS and app notifications for traffic events, accidents, and emergencies.")
st.markdown("---")

# ─── Initialize Alert Manager ───────────────────────────────────────────────
from src.alerts.alert_manager import AlertManager, AlertType, AlertPriority
from src.alerts.notification_sender import NotificationSender

# Initialize or get from session
if "alert_manager" not in st.session_state:
    notif_sender = NotificationSender()
    alert_mgr = AlertManager(notification_enabled=True)
    alert_mgr.set_notification_sender(notif_sender)
    st.session_state["alert_manager"] = alert_mgr
    st.session_state["notification_sender"] = notif_sender
else:
    alert_mgr = st.session_state["alert_manager"]
    notif_sender = st.session_state["notification_sender"]

# ─── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.header("Alert Settings")
sms_enabled = st.sidebar.checkbox("Enable SMS Alerts", value=False)
notification_enabled = st.sidebar.checkbox("Enable App Notifications", value=True)
min_priority = st.sidebar.selectbox("Minimum Priority", ["LOW", "MEDIUM", "HIGH", "CRITICAL"], index=1)
cooldown = st.sidebar.slider("Alert Cooldown (seconds)", 5, 120, 30, 5)

# Update alert manager settings
alert_mgr.min_priority = AlertPriority[min_priority]
alert_mgr.cooldown_seconds = cooldown

if sms_enabled:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Twilio SMS Config")
    twilio_sid = st.sidebar.text_input("Account SID", type="password", key="twilio_sid")
    twilio_token = st.sidebar.text_input("Auth Token", type="password", key="twilio_token")
    twilio_from = st.sidebar.text_input("From Number", placeholder="+1234567890", key="twilio_from")
    twilio_to = st.sidebar.text_input("To Numbers (comma-separated)", placeholder="+91XXXXXXXXXX", key="twilio_to")

    if twilio_sid and twilio_token and twilio_from:
        try:
            from src.alerts.sms_sender import SMSSender
            sms_sender = SMSSender(
                account_sid=twilio_sid,
                auth_token=twilio_token,
                from_number=twilio_from,
                to_numbers=[n.strip() for n in twilio_to.split(",") if n.strip()],
            )
            alert_mgr.set_sms_sender(sms_sender)
            st.sidebar.success("Twilio SMS connected!")
        except Exception as e:
            st.sidebar.error(f"Twilio error: {e}")

# ─── Auto-generate alerts from detection results ───────────────────────────
accident_events = st.session_state.get("accident_events", [])
emergency_events = st.session_state.get("emergency_events", [])
final_counts = st.session_state.get("final_counts", {})

# Create alerts from accident events
for event in accident_events:
    severity_map = {"critical": AlertPriority.CRITICAL, "high": AlertPriority.HIGH,
                    "medium": AlertPriority.MEDIUM, "low": AlertPriority.LOW}
    alert_mgr.create_alert(
        alert_type=AlertType.ACCIDENT,
        priority=severity_map.get(event.severity, AlertPriority.MEDIUM),
        title=f"{event.event_type.replace('_', ' ').title()} detected",
        message=event.description,
        camera_id="cam_01",
    )

# Create alerts from emergency events
for event in emergency_events:
    alert_mgr.create_alert(
        alert_type=AlertType.EMERGENCY_VEHICLE,
        priority=AlertPriority.HIGH,
        title=f"Emergency vehicle: {event.vehicle_type}",
        message=f"{event.vehicle_type} detected at frame {event.frame_number}",
        camera_id="cam_01",
    )

# Heavy traffic alert
if final_counts.get("total", 0) >= 30:
    alert_mgr.create_alert(
        alert_type=AlertType.HEAVY_TRAFFIC,
        priority=AlertPriority.MEDIUM,
        title="Heavy traffic detected",
        message=f"Total vehicles: {final_counts['total']}",
        camera_id="cam_01",
    )

# ─── Main Content ────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Notifications", "Alert Configuration", "Statistics"])

with tab1:
    st.subheader("Recent Notifications")

    # Load from NotificationSender
    notifications = notif_sender.get_all(last_n=50)

    if notifications:
        unread = notif_sender.get_unread()
        st.info(f"{len(unread)} unread notification(s) out of {len(notifications)} total.")

        if st.button("Mark All as Read"):
            notif_sender.mark_all_read()
            st.rerun()

        for notif in reversed(notifications[-20:]):
            priority_icon = {
                "CRITICAL": ":red_circle:",
                "HIGH": ":orange_circle:",
                "MEDIUM": ":large_yellow_circle:",
                "LOW": ":white_circle:",
            }.get(notif.get("priority", ""), ":white_circle:")

            read_status = "" if notif.get("read") else " :new:"
            ts = datetime.fromtimestamp(notif["timestamp"]).strftime("%H:%M:%S") if notif.get("timestamp") else ""

            with st.expander(f"{priority_icon} {notif['title']}{read_status} -- {ts}"):
                st.markdown(f"**Type:** {notif.get('type', 'N/A')}")
                st.markdown(f"**Message:** {notif.get('message', '')}")
                st.markdown(f"**Location:** {notif.get('location', 'N/A')}")
                st.markdown(f"**Camera:** {notif.get('camera_id', 'N/A')}")
    else:
        st.info("No notifications yet. Run detection on other pages to generate real alerts.")

    # Manual alert creation
    st.markdown("---")
    st.subheader("Create Manual Alert")
    with st.form("manual_alert"):
        m_type = st.selectbox("Alert Type", [t.value for t in AlertType])
        m_priority = st.selectbox("Priority", [p.name for p in AlertPriority])
        m_title = st.text_input("Title", placeholder="Heavy traffic at junction")
        m_message = st.text_area("Message", placeholder="Traffic congestion detected...")
        m_location = st.text_input("Location", placeholder="MG Road Junction")

        if st.form_submit_button("Send Alert"):
            alert = alert_mgr.create_alert(
                alert_type=AlertType(m_type),
                priority=AlertPriority[m_priority],
                title=m_title,
                message=m_message,
                location=m_location,
            )
            if alert:
                st.success(f"Alert {alert.alert_id} created and dispatched!")
                st.rerun()
            else:
                st.warning("Alert suppressed by cooldown or priority filter.")

with tab2:
    st.subheader("Alert Rules Configuration")

    st.markdown("### Alert Types & Channels")

    alert_types = {
        "Accident Detected": {"sms": True, "app": True, "priority": "CRITICAL"},
        "Illegal Vehicle Spotted": {"sms": True, "app": True, "priority": "HIGH"},
        "Heavy Traffic": {"sms": False, "app": True, "priority": "MEDIUM"},
        "Emergency Vehicle": {"sms": False, "app": True, "priority": "MEDIUM"},
        "Signal Override": {"sms": False, "app": True, "priority": "LOW"},
    }

    for alert_name, config in alert_types.items():
        with st.expander(f"{alert_name} -- {config['priority']}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.checkbox("SMS", value=config["sms"], key=f"sms_{alert_name}")
            with col2:
                st.checkbox("App Notification", value=config["app"], key=f"app_{alert_name}")
            with col3:
                st.selectbox("Priority", ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                           index=["LOW", "MEDIUM", "HIGH", "CRITICAL"].index(config["priority"]),
                           key=f"pri_{alert_name}")

with tab3:
    st.subheader("Alert Statistics")

    stats = alert_mgr.get_alert_stats()

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Alerts", stats.get("total", 0))
    with col2:
        st.metric("Accidents", stats.get("accident", 0))
    with col3:
        st.metric("Illegal Vehicles", stats.get("illegal_vehicle", 0))
    with col4:
        st.metric("Heavy Traffic", stats.get("heavy_traffic", 0))
    with col5:
        st.metric("Emergency", stats.get("emergency_vehicle", 0))

    if st.button("Clear All Alerts"):
        alert_mgr.clear()
        notif_sender.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("### Alert Flow")
    st.markdown("""
    ```
    Event Detected -> Priority Check -> Cooldown Check -> Dispatch
                                                         |-- SMS (Twilio) -> Authorities
                                                         |-- App Notification -> Dashboard
                                                         +-- Webhook (optional) -> External Systems
    ```
    """)
