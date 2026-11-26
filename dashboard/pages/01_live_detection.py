"""Live Detection page - Upload video and run real-time detection + tracking."""

import tempfile
import time

import cv2
import numpy as np
import streamlit as st

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

from config.settings import PipelineConfig, DetectionConfig, TrackingConfig, VEHICLE_CLASSES
from src.pipeline.video_pipeline import VideoPipeline


st.set_page_config(page_title="Live Detection", layout="wide")
st.title("Live Vehicle Detection & Tracking")

# ─── Sidebar Controls ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")

    model_name = st.selectbox(
        "Detection Model",
        ["yolov8", "yolov9", "yolov10", "yolov8m_coco"],
        help="Custom models: yolov8/v9/v10 (9 Indian classes). "
             "yolov8m_coco: pre-trained on 80 COCO classes (works on any video).",
    )
    tracker_type = st.selectbox("Tracker", ["bytetrack", "deepsort"])
    confidence = st.slider("Confidence Threshold", 0.1, 1.0, 0.3, 0.05)
    line_position = st.slider("Counting Line Position", 0.1, 0.9, 0.6, 0.05)
    direction = st.selectbox("Count Direction", ["both", "down", "up"])
    max_frames = st.number_input("Max Frames (0 = all)", 0, 10000, 0, 100)

# ─── Video Source ─────────────────────────────────────────────────────────────
st.markdown("### Upload a Traffic Video")
uploaded_file = st.file_uploader(
    "Choose a video file",
    type=["mp4", "avi", "mov", "mkv"],
)

if uploaded_file is not None:
    # Save uploaded file to temp
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded_file.read())
    tfile.flush()

    st.video(uploaded_file)

    if st.button("Run Detection & Tracking", type="primary"):
        # Build config
        config = PipelineConfig()
        config.detection = DetectionConfig(
            model_name=model_name,
            confidence_threshold=confidence,
        )
        config.tracking = TrackingConfig(tracker_type=tracker_type)
        config.counting.line_y_fraction = line_position
        config.counting.direction = direction

        # Initialize pipeline
        pipeline = VideoPipeline(config)

        # UI placeholders
        col_video, col_stats = st.columns([3, 1])

        with col_video:
            frame_placeholder = st.empty()
        with col_stats:
            count_placeholder = st.empty()
            density_placeholder = st.empty()
            fps_placeholder = st.empty()

        progress_bar = st.progress(0)
        status_text = st.empty()

        # Process video
        cap = cv2.VideoCapture(tfile.name)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

        frame_limit = max_frames if max_frames > 0 else total_frames

        frame_idx = 0
        density_history = []
        all_tracks = []
        all_detections = []
        cap = cv2.VideoCapture(tfile.name)

        while cap.isOpened() and frame_idx < frame_limit:
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = frame_idx / video_fps
            result = pipeline.process_frame(frame, timestamp)
            density_history.append(result.density)
            all_tracks.extend(result.tracks)
            all_detections.extend(result.detections)

            # Update video display (every 3rd frame for performance)
            if frame_idx % 3 == 0:
                rgb_frame = cv2.cvtColor(result.annotated_frame, cv2.COLOR_BGR2RGB)
                frame_placeholder.image(rgb_frame, channels="RGB", use_container_width=True)

                # Update stats
                count_placeholder.markdown("### Vehicle Counts")
                for cls, cnt in sorted(result.counts.items()):
                    count_placeholder.markdown(f"**{cls}**: {cnt}")

                density_placeholder.markdown(f"### Density: {result.density.value}")
                fps_placeholder.markdown(f"**FPS**: {result.fps:.1f}")

            # Progress
            progress = (frame_idx + 1) / frame_limit
            progress_bar.progress(progress)
            status_text.text(f"Frame {frame_idx + 1}/{frame_limit}")

            frame_idx += 1

        cap.release()
        progress_bar.progress(1.0)
        status_text.text("Processing complete!")

        # Final results
        st.markdown("---")
        st.markdown("### Final Results")
        final_counts = pipeline.counter.get_counts()

        # Filter out non-vehicle classes (like 'person') for display
        vehicle_counts = {k: v for k, v in final_counts.items()
                         if k.lower() not in ("person", "total")}
        vehicle_total = sum(vehicle_counts.values())
        vehicle_counts["total"] = vehicle_total

        if vehicle_counts:
            num_cols = min(len(vehicle_counts), 9)
            cols = st.columns(num_cols)
            for i, (cls, cnt) in enumerate(sorted(vehicle_counts.items())):
                with cols[i % num_cols]:
                    st.metric(cls.replace("_", " ").title(), cnt)

        # Show crossing vs unique breakdown
        if hasattr(pipeline.counter, 'get_crossing_counts'):
            crossing = pipeline.counter.get_crossing_counts()
            unique = pipeline.counter.get_unique_vehicle_counts()
            if crossing["total"] > 0:
                st.caption(f"Line crossings: {crossing['total']} | Unique vehicles seen: {unique['total']}")
            else:
                st.caption(f"Unique vehicles detected: {unique['total']} (no line crossings in this video)")

        # Store data in session for other pages
        st.session_state["aggregator"] = pipeline.get_aggregator()
        st.session_state["final_counts"] = vehicle_counts
        st.session_state["density_history"] = density_history
        st.session_state["all_tracks"] = all_tracks
        st.session_state["all_detections"] = all_detections
        st.session_state["video_fps"] = video_fps
        st.session_state["total_frames"] = frame_idx

else:
    st.info("Upload a traffic video to start detection and tracking.")
    st.markdown("""
    **Supported formats**: MP4, AVI, MOV, MKV

    **Tips**:
    - Use 720p or higher resolution for best results
    - Adjust the counting line position to match the road in your video
    - ByteTrack is faster; Deep SORT is more accurate for crowded scenes
    """)
