"""Number plate detection using YOLOv8 or OpenCV cascade."""

from typing import List, Tuple, Optional

import cv2
import numpy as np


class PlateDetector:
    """Detects number plates in vehicle images/frames.

    Supports two modes:
    1. YOLOv8 custom-trained plate detection model
    2. OpenCV Haar cascade fallback
    """

    def __init__(
        self,
        mode: str = "cascade",
        model_path: Optional[str] = None,
        confidence: float = 0.5,
        cascade_path: Optional[str] = None,
    ):
        self.mode = mode
        self.confidence = confidence

        if mode == "yolo" and model_path:
            from ultralytics import YOLO
            self.model = YOLO(model_path)
        else:
            self.mode = "cascade"
            if cascade_path:
                self.cascade = cv2.CascadeClassifier(cascade_path)
            else:
                # Use OpenCV's built-in Russian plate cascade (works for many plate types)
                cascade_file = cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
                self.cascade = cv2.CascadeClassifier(cascade_file)

    def detect_plates(
        self, frame: np.ndarray
    ) -> List[Tuple[int, int, int, int]]:
        """Detect number plate regions in a frame.

        Args:
            frame: BGR image as numpy array.

        Returns:
            List of bounding boxes (x1, y1, x2, y2) for detected plates.
        """
        if self.mode == "yolo":
            return self._detect_yolo(frame)
        return self._detect_cascade(frame)

    def _detect_yolo(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        results = self.model(frame, conf=self.confidence, verbose=False)[0]
        plates = []
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int).tolist()
            plates.append((x1, y1, x2, y2))
        return plates

    def _detect_cascade(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        detections = self.cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(60, 20),
            maxSize=(300, 100),
        )

        plates = []
        for (x, y, w, h) in detections:
            plates.append((x, y, x + w, y + h))
        return plates

    def extract_plate_region(
        self, frame: np.ndarray, bbox: Tuple[int, int, int, int], padding: int = 5
    ) -> np.ndarray:
        """Extract and preprocess a plate region for OCR.

        Args:
            frame: Full BGR image.
            bbox: Plate bounding box (x1, y1, x2, y2).
            padding: Extra pixels around the plate.

        Returns:
            Preprocessed plate image for OCR.
        """
        h, w = frame.shape[:2]
        x1 = max(0, bbox[0] - padding)
        y1 = max(0, bbox[1] - padding)
        x2 = min(w, bbox[2] + padding)
        y2 = min(h, bbox[3] + padding)

        plate_img = frame[y1:y2, x1:x2]

        # Preprocess for better OCR
        plate_img = cv2.resize(plate_img, (300, 100))
        gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        gray = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        return gray
