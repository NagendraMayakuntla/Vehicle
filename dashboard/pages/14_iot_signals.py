"""Dashboard page for IoT Traffic Signal Control - Real MQTTSignalController."""

import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="IoT Signal Control", page_icon=":vertical_traffic_light:", layout="wide")
st.title(":vertical_traffic_light: IoT Traffic Signal Control")
st.markdown("Control physical traffic signals via MQTT / Raspberry Pi.")
st.markdown("---")

# ─── Initialize MQTT Controller ─────────────────────────────────────────────
from src.iot.mqtt_signal_controller import MQTTSignalController

# ─── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.header("IoT Settings")
simulation_mode = st.sidebar.checkbox("Simulation Mode", value=True)
broker_host = st.sidebar.text_input("MQTT Broker", value="localhost")
broker_port = st.sidebar.number_input("MQTT Port", value=1883)

# Initialize controller
if "mqtt_controller" not in st.session_state:
    st.session_state.mqtt_controller = MQTTSignalController(
        broker_host=broker_host,
        broker_port=broker_port,
        simulate=simulation_mode,
    )

controller = st.session_state.mqtt_controller

# Try to connect if not in simulation mode
if not simulation_mode:
    if controller.is_connected:
        st.sidebar.success(f"Connected to {broker_host}:{broker_port}")
    else:
        st.sidebar.warning("MQTT connection failed. Running in simulation mode.")
else:
    st.sidebar.info("Running in simulation mode (no MQTT broker needed)")

# ─── Main Content ────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Signal Control", "Hardware Setup", "Signal Log"])

with tab1:
    st.subheader("4-Way Intersection Signal Control")

    # Get real signal states from controller
    states = controller.get_all_states()

    signal_colors = {
        "red": ":red_circle:",
        "yellow": ":large_yellow_circle:",
        "green": ":green_circle:",
    }

    # Visual intersection layout
    st.markdown("### Intersection View")

    def get_state(direction):
        info = states.get(direction, {})
        return info.get("state", "red") if isinstance(info, dict) else "red"

    # North
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        n_state = get_state("north")
        st.markdown(f"### :arrow_up: NORTH {signal_colors.get(n_state, ':white_circle:')} **{n_state.upper()}**")

    # West and East
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        w_state = get_state("west")
        st.markdown(f"### :arrow_left: WEST {signal_colors.get(w_state, ':white_circle:')} **{w_state.upper()}**")
    with col2:
        st.markdown("### :motorway: ")
    with col3:
        e_state = get_state("east")
        st.markdown(f"### :arrow_right: EAST {signal_colors.get(e_state, ':white_circle:')} **{e_state.upper()}**")

    # South
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        s_state = get_state("south")
        st.markdown(f"### :arrow_down: SOUTH {signal_colors.get(s_state, ':white_circle:')} **{s_state.upper()}**")

    st.markdown("---")

    # Manual Controls
    st.markdown("### Manual Control")
    col1, col2, col3, col4 = st.columns(4)

    directions = ["north", "south", "east", "west"]
    cols = [col1, col2, col3, col4]

    for direction, col in zip(directions, cols):
        with col:
            st.markdown(f"**{direction.upper()}**")
            if st.button(f":green_circle: Green", key=f"green_{direction}"):
                controller.set_signal(direction, "green")
                for d in directions:
                    if d != direction:
                        controller.set_signal(d, "red")
                st.rerun()

    st.markdown("---")

    # Emergency override - use real detection data if available
    st.markdown("### Emergency Override")

    # Auto-trigger from emergency detection
    signal_ctrl = st.session_state.get("signal_controller")
    if signal_ctrl and signal_ctrl.is_in_emergency_mode:
        sig_states = signal_ctrl.get_signal_states()
        for sig_id, sig_info in sig_states.items():
            if sig_info["is_emergency"] and sig_info["state"] == "green":
                st.warning(f"Emergency override active: {sig_info['direction'].upper()} -> GREEN")
                controller.set_signal(sig_info["direction"], "green")
                for d in directions:
                    if d != sig_info["direction"]:
                        controller.set_signal(d, "red")

    col1, col2 = st.columns([2, 1])
    with col1:
        emergency_dir = st.selectbox("Emergency Direction", directions)
    with col2:
        if st.button("Activate Emergency Override", type="primary"):
            controller.set_signal(emergency_dir, "green")
            for d in directions:
                if d != emergency_dir:
                    controller.set_signal(d, "red")
            st.success(f"Emergency override: {emergency_dir.upper()} -> GREEN")
            st.rerun()

    if st.button("All RED (Reset)"):
        for d in directions:
            controller.set_signal(d, "red")
        st.rerun()

    # Mode indicator
    mode = "Simulation" if simulation_mode else "MQTT Live"
    st.caption(f"Mode: {mode} | Broker: {broker_host}:{broker_port}")

with tab2:
    st.subheader("Raspberry Pi Hardware Setup")

    st.markdown("### Components Required")
    st.markdown("""
    | Component | Quantity | Cost (approx) |
    |-----------|----------|---------------|
    | Raspberry Pi 4 | 1 | Rs.3,500 |
    | 4-Channel Relay Module | 1 | Rs.150 |
    | LED Lights (R/Y/G) | 12 (3 per direction) | Rs.100 |
    | Breadboard + Jumper Wires | 1 set | Rs.100 |
    | Power Supply (5V) | 1 | Rs.200 |
    | **Total** | | **~Rs.4,050** |
    """)

    st.markdown("### GPIO Pin Mapping")
    st.code("""
    # BCM Pin Numbering
    NORTH:  Red=GPIO17,  Yellow=GPIO27, Green=GPIO22
    SOUTH:  Red=GPIO23,  Yellow=GPIO24, Green=GPIO25
    EAST:   Red=GPIO5,   Yellow=GPIO6,  Green=GPIO13
    WEST:   Red=GPIO16,  Yellow=GPIO20, Green=GPIO21
    """, language="python")

    st.markdown("### MQTT Setup")
    st.code("""
# Install Mosquitto MQTT broker
sudo apt install mosquitto mosquitto-clients

# Start broker
sudo systemctl start mosquitto
sudo systemctl enable mosquitto

# Test
mosquitto_pub -t "traffic/signal/north/state" -m '{"direction":"north","state":"green"}'
    """, language="bash")

with tab3:
    st.subheader("Signal Change Log")

    change_log = controller.get_change_log()
    if change_log:
        log_data = []
        for entry in change_log:
            if isinstance(entry, dict):
                log_data.append(entry)
            else:
                log_data.append({
                    "Time": datetime.fromtimestamp(entry.timestamp).strftime("%H:%M:%S") if hasattr(entry, 'timestamp') else "N/A",
                    "Direction": entry.direction if hasattr(entry, 'direction') else "N/A",
                    "Old State": entry.old_state if hasattr(entry, 'old_state') else "N/A",
                    "New State": entry.new_state if hasattr(entry, 'new_state') else "N/A",
                    "Reason": entry.reason if hasattr(entry, 'reason') else "manual",
                })
        if log_data:
            st.dataframe(pd.DataFrame(log_data), use_container_width=True)
    else:
        st.info("Signal changes will be logged here. Use the controls above to change signals.")

    # Show MQTT messages if connected
    if not simulation_mode:
        st.markdown("### Recent MQTT Messages")
        mqtt_log = controller.get_mqtt_log() if hasattr(controller, 'get_mqtt_log') else []
        if mqtt_log:
            for msg in mqtt_log[-10:]:
                st.code(f"Topic: {msg.get('topic', 'N/A')}\nPayload: {msg.get('payload', 'N/A')}")
        else:
            st.info("No MQTT messages yet.")
