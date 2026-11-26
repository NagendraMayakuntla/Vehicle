"""Dashboard page for Automatic Number Plate Recognition (ANPR) - Real detection."""

import tempfile
import streamlit as st
import pandas as pd
import json
import cv2
import numpy as np
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="ANPR System", page_icon=":oncoming_automobile:", layout="wide")
st.title(":oncoming_automobile: Number Plate Recognition (ANPR)")
st.markdown("Detect and read vehicle number plates. Track illegal/wanted vehicles.")
st.markdown("---")

# ─── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.header("ANPR Settings")
detector_mode = st.sidebar.selectbox("Plate Detector", ["cascade", "yolo"])
ocr_confidence = st.sidebar.slider("OCR Min Confidence", 0.1, 1.0, 0.5, 0.05)
show_preprocessing = st.sidebar.checkbox("Show Preprocessing Steps", value=False)

# ─── Main Content ────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Plate Detection", "Flagged Vehicles Database", "Detection Log"])

with tab1:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Upload Image / Video")
        upload_type = st.radio("Input Type", ["Image", "Video"], horizontal=True)

        if upload_type == "Image":
            uploaded = st.file_uploader("Upload vehicle image", type=["jpg", "jpeg", "png", "bmp"])
            if uploaded:
                # Read image
                file_bytes = np.frombuffer(uploaded.read(), np.uint8)
                img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                st.image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), caption="Uploaded Image", use_container_width=True)

                if st.button("Detect Plates", type="primary"):
                    from src.anpr.plate_detector import PlateDetector
                    from src.anpr.plate_reader import PlateReader

                    with st.spinner("Detecting plates..."):
                        # Initialize detector
                        plate_detector = PlateDetector(mode=detector_mode)
                        plates = plate_detector.detect_plates(img)

                        if plates:
                            st.success(f"Found {len(plates)} plate(s)!")

                            # Initialize OCR reader
                            try:
                                reader = PlateReader(gpu=False)
                                ocr_available = True
                            except Exception as e:
                                st.warning(f"EasyOCR not available: {e}")
                                ocr_available = False

                            detection_results = []
                            annotated = img.copy()

                            for i, bbox in enumerate(plates):
                                x1, y1, x2, y2 = bbox
                                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

                                plate_text = "N/A"
                                confidence = 0.0

                                if ocr_available:
                                    plate_img = plate_detector.extract_plate_region(img, bbox)
                                    plate_text, confidence = reader.read_plate(plate_img)
                                    plate_text = plate_text or "Unreadable"

                                    if show_preprocessing:
                                        st.image(plate_img, caption=f"Plate {i+1} preprocessed", width=300)

                                    cv2.putText(annotated, f"{plate_text} ({confidence:.2f})",
                                              (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                                detection_results.append({
                                    "Plate #": i + 1,
                                    "Text": plate_text,
                                    "Confidence": round(confidence, 2),
                                    "BBox": f"({x1},{y1},{x2},{y2})",
                                })

                                # Check against flagged database
                                if plate_text and plate_text != "N/A":
                                    try:
                                        from src.anpr.illegal_vehicle_checker import IllegalVehicleChecker
                                        checker = IllegalVehicleChecker()
                                        match = checker.check_plate(plate_text)
                                        if match.is_flagged:
                                            reason = match.record.reason if match.record else "N/A"
                                            st.error(f"ALERT: Plate {plate_text} is FLAGGED! Reason: {reason}")
                                            detection_results[-1]["Flagged"] = True
                                            detection_results[-1]["Reason"] = reason
                                    except Exception:
                                        pass

                            st.image(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB),
                                   caption="Detected Plates", use_container_width=True)
                            st.dataframe(pd.DataFrame(detection_results), use_container_width=True)

                            # Store in session for log
                            if "anpr_log" not in st.session_state:
                                st.session_state["anpr_log"] = []
                            st.session_state["anpr_log"].extend(detection_results)

                        else:
                            st.warning("No plates detected in this image. Try adjusting the image or detector mode.")

        else:
            uploaded = st.file_uploader("Upload traffic video", type=["mp4", "avi", "mov"])
            if uploaded:
                st.video(uploaded)
                st.info("For video ANPR, run detection on Live Detection page first, then plates are detected on tracked vehicles.")

    with col2:
        st.subheader("Detection Results")
        if "anpr_log" in st.session_state and st.session_state["anpr_log"]:
            st.dataframe(pd.DataFrame(st.session_state["anpr_log"]), use_container_width=True)
        else:
            st.info("Upload an image and click **Detect Plates** to see results.")

        st.markdown("### Supported Formats")
        st.markdown("""
        **Indian Number Plate Format:**
        - `KA 01 AB 1234` (Karnataka)
        - `MH 02 CD 5678` (Maharashtra)
        - `TN 03 EF 9012` (Tamil Nadu)

        **Format:** `[State][District][Series][Number]`
        """)

with tab2:
    st.subheader("Flagged Vehicles Database")

    # Load database
    db_path = Path("data/flagged_vehicles.json")
    if db_path.exists():
        with open(db_path, "r") as f:
            data = json.load(f)

        vehicles = data.get("flagged_vehicles", [])
        if vehicles:
            df = pd.DataFrame(vehicles)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No flagged vehicles in database.")
    else:
        st.warning("Database file not found. Add a vehicle below to create it.")

    st.markdown("---")
    st.subheader("Add Flagged Vehicle")

    with st.form("add_vehicle"):
        col1, col2 = st.columns(2)
        with col1:
            plate = st.text_input("Plate Number", placeholder="KA01AB1234")
            reason = st.selectbox("Reason", ["stolen", "wanted", "blacklisted", "expired_registration"])
            owner = st.text_input("Owner Name (optional)")
        with col2:
            v_type = st.selectbox("Vehicle Type", ["Car", "Bike", "Bus", "Truck", "Auto", "Scooty"])
            priority = st.selectbox("Priority", ["critical", "high", "medium", "low"])

        submitted = st.form_submit_button("Add to Database")
        if submitted and plate:
            new_entry = {
                "plate_number": plate.upper().replace(" ", "").replace("-", ""),
                "reason": reason,
                "reported_date": str(pd.Timestamp.now().date()),
                "owner_name": owner,
                "vehicle_type": v_type,
                "priority": priority,
            }

            if db_path.exists():
                with open(db_path, "r") as f:
                    data = json.load(f)
            else:
                data = {"flagged_vehicles": []}

            data["flagged_vehicles"].append(new_entry)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(db_path, "w") as f:
                json.dump(data, f, indent=2)

            st.success(f"Added {plate} to flagged vehicles database!")
            st.rerun()

with tab3:
    st.subheader("Detection Log")

    anpr_log = st.session_state.get("anpr_log", [])
    if anpr_log:
        st.dataframe(pd.DataFrame(anpr_log), use_container_width=True)
        if st.button("Clear Log"):
            st.session_state["anpr_log"] = []
            st.rerun()
    else:
        st.info("Plate detections will be logged here after running detection.")
