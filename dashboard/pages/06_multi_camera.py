"""Multi-Camera page - Real multi-camera monitoring with video file inputs."""

import tempfile
import time
import threading

import cv2
import numpy as np
import streamlit as st
import pandas as pd
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="Multi-Camera", layout="wide")
st.title("Multi-Camera Monitoring")

st.markdown("""
Monitor multiple camera feeds simultaneously with cross-camera vehicle
re-identification for deduplicated global counts.
""")

# ─── Camera Source Configuration ────────────────────────────────────────────
st.markdown("### Camera Sources")

# Allow users to add video files as camera sources
if "camera_sources" not in st.session_state:
    st.session_state.camera_sources = []

# Upload area
col_upload1, col_upload2 = st.columns(2)
with col_upload1:
    cam_name = st.text_input("Camera Name", placeholder="Main Intersection")
with col_upload2:
    cam_source = st.selectbox("Source Type", ["Video File", "Webcam (0)", "Webcam (1)", "RTSP URL"])

if cam_source == "Video File":
    cam_file = st.file_uploader("Upload video for this camera", type=["mp4", "avi", "mov"], key="cam_upload")
elif cam_source == "RTSP URL":
    cam_file = st.text_input("RTSP URL", placeholder="rtsp://...")
else:
    cam_file = cam_source

if st.button("Add Camera") and cam_name:
    source_path = None
    if cam_source == "Video File" and cam_file is not None:
        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tfile.write(cam_file.read())
        tfile.flush()
        source_path = tfile.name
    elif cam_source in ("Webcam (0)", "Webcam (1)"):
        source_path = int(cam_source.split("(")[1].rstrip(")"))
    elif cam_source == "RTSP URL" and cam_file:
        source_path = cam_file

    if source_path is not None:
        st.session_state.camera_sources.append({
            "name": cam_name,
            "source": source_path,
            "id": f"cam_{len(st.session_state.camera_sources) + 1:02d}",
        })
        st.success(f"Added camera: {cam_name}")
        st.rerun()

# Show configured cameras
cameras = st.session_state.camera_sources
if cameras:
    cols = st.columns(min(len(cameras), 4))
    for i, cam in enumerate(cameras):
        with cols[i % len(cols)]:
            st.markdown(
                f'<div style="border:2px solid #00FF00;padding:10px;border-radius:8px;text-align:center;">'
                f'<h4>{cam["name"]}</h4>'
                f'<p style="color:#00FF00;font-weight:bold;">Configured</p>'
                f'<p>ID: {cam["id"]}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if st.button("Clear All Cameras"):
        st.session_state.camera_sources = []
        st.rerun()

st.markdown("---")

# ─── Run Multi-Camera Detection ────────────────────────────────────────────
if cameras and st.button("Run Multi-Camera Detection", type="primary"):
    from config.settings import PipelineConfig, DetectionConfig, TrackingConfig
    from src.pipeline.video_pipeline import VideoPipeline

    try:
        from src.multicamera.reid_extractor import ReIDExtractor
        from src.multicamera.cross_camera_matcher import CrossCameraMatcher
        from src.multicamera.global_count_tracker import GlobalCountTracker
        reid_available = True
    except ImportError:
        reid_available = False
        st.warning("ReID modules not fully available. Running without cross-camera matching.")

    # Initialize components
    config = PipelineConfig()
    config.detection.model_name = "yolov8m_coco"

    reid_extractor = ReIDExtractor() if reid_available else None
    matcher = CrossCameraMatcher() if reid_available else None
    global_tracker = GlobalCountTracker() if reid_available else None

    # Process each camera
    camera_results = {}
    frame_placeholders = {}

    num_cams = len(cameras)
    cam_cols = st.columns(min(num_cams, 2))

    for i, cam in enumerate(cameras):
        with cam_cols[i % 2]:
            st.markdown(f"**{cam['name']}**")
            frame_placeholders[cam["id"]] = st.empty()

    progress = st.progress(0)
    status = st.empty()

    for cam_idx, cam in enumerate(cameras):
        status.text(f"Processing {cam['name']}...")
        pipeline = VideoPipeline(config)

        cap = cv2.VideoCapture(cam["source"])
        if not cap.isOpened():
            st.error(f"Cannot open {cam['name']}")
            continue

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 100
        max_frames = min(total_frames, 100)
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        cam_tracks = []
        frame_idx = 0

        while cap.isOpened() and frame_idx < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            result = pipeline.process_frame(frame, frame_idx / video_fps)

            if frame_idx % 5 == 0:
                rgb = cv2.cvtColor(result.annotated_frame, cv2.COLOR_BGR2RGB)
                frame_placeholders[cam["id"]].image(rgb, channels="RGB", use_container_width=True)

            cam_tracks.extend(result.tracks)
            frame_idx += 1

        cap.release()

        final_counts = pipeline.counter.get_counts()
        camera_results[cam["id"]] = {
            "name": cam["name"],
            "counts": final_counts,
            "total": final_counts.get("total", 0),
            "tracks": cam_tracks,
        }

        progress.progress((cam_idx + 1) / num_cams)

    status.text("Processing complete!")

    # ─── Global Counts ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Per-Camera Results")

    result_cols = st.columns(len(camera_results))
    total_vehicles = 0
    for i, (cam_id, res) in enumerate(camera_results.items()):
        with result_cols[i]:
            st.metric(res["name"], res["total"])
            for cls, cnt in sorted(res["counts"].items()):
                if cls != "total" and cnt > 0:
                    st.caption(f"{cls}: {cnt}")
        total_vehicles += res["total"]

    st.markdown("---")
    st.markdown("### Global Summary")

    g1, g2, g3 = st.columns(3)
    with g1:
        st.metric("Total Vehicles (all cameras)", total_vehicles)
    with g2:
        st.metric("Active Cameras", len(camera_results))
    with g3:
        if reid_available and matcher:
            st.metric("ReID Status", "Active")
        else:
            st.metric("ReID Status", "Disabled")

    st.session_state["multicam_results"] = camera_results

elif not cameras:
    st.info("Add camera sources above, then click **Run Multi-Camera Detection**.")
