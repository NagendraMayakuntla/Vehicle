"""Multi-camera feed manager for concurrent video processing."""

import threading
from queue import Queue, Empty
from typing import Dict, Optional, List

import cv2
import numpy as np

from config.settings import CameraSource


class FeedManager:
    """Manages multiple video sources concurrently using threads."""

    def __init__(self, cameras: List[CameraSource]):
        self.cameras: Dict[str, dict] = {}
        for cam in cameras:
            if cam.enabled:
                self.cameras[cam.id] = {
                    "config": cam,
                    "capture": None,
                    "queue": Queue(maxsize=10),
                    "thread": None,
                    "running": False,
                    "fps": 0.0,
                }

    def start_all(self):
        """Start reading frames from all enabled cameras."""
        for cam_id in self.cameras:
            self.start_camera(cam_id)

    def start_camera(self, cam_id: str):
        """Start a single camera feed."""
        cam = self.cameras.get(cam_id)
        if not cam:
            return

        source = cam["config"].source
        # Convert numeric strings to int (device index)
        try:
            source = int(source)
        except (ValueError, TypeError):
            pass

        cam["capture"] = cv2.VideoCapture(source)
        if not cam["capture"].isOpened():
            return

        cam["running"] = True
        cam["thread"] = threading.Thread(
            target=self._read_frames, args=(cam_id,), daemon=True
        )
        cam["thread"].start()

    def stop_all(self):
        """Stop all camera feeds."""
        for cam_id in self.cameras:
            self.stop_camera(cam_id)

    def stop_camera(self, cam_id: str):
        """Stop a single camera feed."""
        cam = self.cameras.get(cam_id)
        if cam:
            cam["running"] = False
            if cam["thread"]:
                cam["thread"].join(timeout=3.0)
            if cam["capture"] and cam["capture"].isOpened():
                cam["capture"].release()

    def _read_frames(self, cam_id: str):
        """Background thread: continuously read frames into queue."""
        cam = self.cameras[cam_id]
        cap = cam["capture"]

        while cam["running"] and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            queue = cam["queue"]
            if queue.full():
                try:
                    queue.get_nowait()  # Drop oldest frame
                except Empty:
                    pass
            queue.put(frame)

        cam["running"] = False

    def get_frame(self, cam_id: str, timeout: float = 1.0) -> Optional[np.ndarray]:
        """Get the latest frame from a camera (blocking).

        Args:
            cam_id: Camera identifier.
            timeout: Max wait time in seconds.

        Returns:
            BGR frame or None if timeout/unavailable.
        """
        cam = self.cameras.get(cam_id)
        if not cam:
            return None
        try:
            return cam["queue"].get(timeout=timeout)
        except Empty:
            return None

    def get_active_cameras(self) -> List[str]:
        """Get IDs of cameras that are currently running."""
        return [cid for cid, cam in self.cameras.items() if cam["running"]]

    def get_camera_info(self, cam_id: str) -> Optional[Dict]:
        """Get info about a camera."""
        cam = self.cameras.get(cam_id)
        if not cam:
            return None
        return {
            "id": cam_id,
            "name": cam["config"].name,
            "source": cam["config"].source,
            "running": cam["running"],
        }
