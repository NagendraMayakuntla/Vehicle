"""Dashboard page for Accident Detection System - Real detection from video."""

import tempfile
import time

import streamlit as st
import cv2
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="Accident Detection", page_icon=":rotating_light:", layout="wide")
st.title(":rotating_light: Accident Detection System")
st.markdown("Detect sudden stops, collisions, and stationary vehicles in real-time.")
st.markdown("---")

# ─── Sidebar Configuration ──────────────────────────────────────────────────
st.sidebar.header("Accident Detection Settings")
model_name = st.sidebar.selectbox("Detection Model", ["yolov8", "yolov8m_coco", "yolov9", "yolov10"])
decel_threshold = st.sidebar.slider("Deceleration Threshold (px/frame)", 5.0, 30.0, 15.0, 1.0)
collision_iou = st.sidebar.slider("Collision IoU Threshold", 0.1, 0.8, 0.3, 0.05)
stationary_frames = st.sidebar.slider("Stationary Alert (frames)", 30, 300, 90, 10)
cooldown = st.sidebar.slider("Alert Cooldown (seconds)", 5.0, 60.0, 10.0, 5.0)

# ─── Main Content ────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Live Detection", "Event Log", "Statistics"])

with tab1:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Video Feed")
        uploaded = st.file_uploader("Upload traffic video", type=["mp4", "avi", "mov"])

        if uploaded:
            st.video(uploaded)

    with col2:
        st.subheader("Detection Types")
        st.markdown("""
        - **Sudden Stop** - Vehicle decelerates rapidly
        - **Collision** - Two vehicles overlap unexpectedly
        - **Stationary** - Vehicle stops in traffic lane
        """)

        st.markdown("### Alert Severity")
        st.markdown("""
        - :red_circle: **Critical** - Confirmed collision
        - :orange_circle: **High** - Severe sudden stop
        - :large_yellow_circle: **Medium** - Moderate event
        - :white_circle: **Low** - Stationary vehicle
        """)

    if uploaded and st.button("Run Accident Detection", type="primary"):
        from config.settings import PipelineConfig, DetectionConfig, TrackingConfig, AccidentDetectionConfig
        from src.pipeline.video_pipeline import VideoPipeline
        from src.accident_detection.accident_detector import AccidentDetector

        # Save uploaded file
        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tfile.write(uploaded.getvalue())
        tfile.flush()

        # Initialize pipeline
        config = PipelineConfig()
        config.detection.model_name = model_name
        config.detection.confidence_threshold = 0.3
        pipeline = VideoPipeline(config)

        # Initialize accident detector
        detector = AccidentDetector(
            deceleration_threshold=decel_threshold,
            collision_iou_threshold=collision_iou,
            stationary_frames=stationary_frames,
            cooldown_seconds=cooldown,
        )

        # Process video
        cap = cv2.VideoCapture(tfile.name)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

        frame_placeholder = st.empty()
        event_placeholder = st.empty()
        progress_bar = st.progress(0)
        status_text = st.empty()

        all_events = []
        frame_idx = 0
        cap = cv2.VideoCapture(tfile.name)

        while cap.isOpened() and frame_idx < total_frames:
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = frame_idx / video_fps
            result = pipeline.process_frame(frame, timestamp)

            # Run accident detection on tracks
            events = detector.update(result.tracks, frame_idx)
            all_events.extend(events)

            # Show annotated frame with accident annotations
            annotated = result.annotated_frame.copy()
            for event in events:
                loc = event.location
                color = (0, 0, 255) if event.severity in ("critical", "high") else (0, 165, 255)
                cv2.circle(annotated, (int(loc[0]), int(loc[1])), 30, color, 3)
                cv2.putText(
                    annotated, f"{event.event_type} ({event.severity})",
                    (int(loc[0]) - 50, int(loc[1]) - 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
                )

            if frame_idx % 3 == 0:
                rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
                frame_placeholder.image(rgb, channels="RGB", use_container_width=True)

            if events:
                event_placeholder.warning(f"Event detected: {events[0].event_type} - {events[0].description}")

            progress_bar.progress((frame_idx + 1) / total_frames)
            status_text.text(f"Frame {frame_idx + 1}/{total_frames} | Events: {len(all_events)}")
            frame_idx += 1

        cap.release()
        progress_bar.progress(1.0)
        status_text.text(f"Complete! {len(all_events)} event(s) detected.")

        # Store results
        st.session_state["accident_events"] = all_events
        st.session_state["accident_active_tracks"] = len(detector._track_history)

with tab2:
    st.subheader("Accident Event Log")

    events = st.session_state.get("accident_events", [])

    if events:
        event_data = []
        for e in events:
            event_data.append({
                "Event ID": e.event_id,
                "Type": e.event_type,
                "Severity": e.severity,
                "Frame": e.frame_number,
                "Vehicles": ", ".join([f"#{tid}" for tid in e.involved_track_ids]),
                "Confidence": round(e.confidence, 2),
                "Description": e.description,
            })
        st.dataframe(pd.DataFrame(event_data), use_container_width=True)
    else:
        st.info("No events detected yet. Run accident detection on a video first.")

with tab3:
    st.subheader("Accident Statistics")

    events = st.session_state.get("accident_events", [])

    col1, col2, col3, col4 = st.columns(4)
    collisions = len([e for e in events if e.event_type == "collision"])
    sudden_stops = len([e for e in events if e.event_type == "sudden_stop"])
    stationary = len([e for e in events if e.event_type == "stationary_vehicle"])

    with col1:
        st.metric("Total Events", len(events))
    with col2:
        st.metric("Collisions", collisions)
    with col3:
        st.metric("Sudden Stops", sudden_stops)
    with col4:
        st.metric("Stationary", stationary)

    if events:
        st.markdown("---")
        # Severity distribution
        import plotly.express as px
        severity_counts = pd.Series([e.severity for e in events]).value_counts()
        fig = px.pie(names=severity_counts.index, values=severity_counts.values, title="Event Severity Distribution")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("### How It Works")
    st.markdown("""
    1. **Vehicle Tracking** - Each vehicle is tracked with a unique ID using Deep SORT / ByteTrack
    2. **Speed Analysis** - Vehicle speed is computed from centroid displacement across frames
    3. **Sudden Stop Detection** - If speed drops from > 8 px/frame to < 1 px/frame, it's flagged
    4. **Collision Detection** - If two moving vehicle bounding boxes overlap (IoU > threshold), it's flagged
    5. **Stationary Detection** - If a vehicle remains stationary for > N frames in a traffic lane
    6. **Alert Dispatch** - Events trigger SMS / app notifications to authorities
    """)
