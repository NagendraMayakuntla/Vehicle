"""Global deduplicated vehicle count tracker across all cameras."""

from typing import Dict, Set


class GlobalCountTracker:
    """Maintains deduplicated vehicle counts across all cameras.

    Uses global IDs from CrossCameraMatcher to ensure each physical
    vehicle is only counted once, even if seen by multiple cameras.
    """

    def __init__(self):
        self.global_counts: Dict[str, Set[int]] = {}  # class_name -> set of global_ids
        self.camera_counts: Dict[str, Dict[str, int]] = {}  # camera_id -> class_counts

    def register(self, global_id: int, class_name: str, camera_id: str):
        """Register a vehicle observation.

        Args:
            global_id: Global vehicle ID from CrossCameraMatcher.
            class_name: Vehicle class name.
            camera_id: Camera that observed this vehicle.
        """
        if class_name not in self.global_counts:
            self.global_counts[class_name] = set()
        self.global_counts[class_name].add(global_id)

        # Track per-camera counts
        if camera_id not in self.camera_counts:
            self.camera_counts[camera_id] = {}
        if class_name not in self.camera_counts[camera_id]:
            self.camera_counts[camera_id][class_name] = 0
        self.camera_counts[camera_id][class_name] += 1

    def get_total_counts(self) -> Dict[str, int]:
        """Get deduplicated counts per class across all cameras."""
        counts = {cls: len(ids) for cls, ids in self.global_counts.items()}
        counts["total"] = sum(counts.values())
        return counts

    def get_camera_counts(self, camera_id: str) -> Dict[str, int]:
        """Get raw counts for a specific camera."""
        return self.camera_counts.get(camera_id, {}).copy()

    def get_total_unique_vehicles(self) -> int:
        """Get total number of unique vehicles seen across all cameras."""
        all_ids = set()
        for ids in self.global_counts.values():
            all_ids.update(ids)
        return len(all_ids)

    def reset(self):
        self.global_counts.clear()
        self.camera_counts.clear()
