"""Cross-camera vehicle matching using appearance features."""

from typing import Dict, Optional

import numpy as np
from scipy.spatial.distance import cosine


class CrossCameraMatcher:
    """Matches vehicles across camera feeds using appearance similarity.

    Maintains a gallery of known vehicle features. When a new vehicle
    is observed, it is matched against the gallery using cosine similarity.
    If a match is found, the same global ID is returned; otherwise, a new
    global ID is assigned.
    """

    def __init__(self, similarity_threshold: float = 0.7):
        """
        Args:
            similarity_threshold: Minimum cosine similarity for a match (0-1).
        """
        self.threshold = similarity_threshold
        self.gallery: Dict[int, np.ndarray] = {}  # global_id -> feature_vector
        self.next_id = 0
        self.match_log = []  # For debugging

    def match_or_register(
        self,
        feature: np.ndarray,
        camera_id: str,
        local_track_id: int,
    ) -> int:
        """Find a matching global ID or register as new.

        Args:
            feature: 512-dim appearance feature vector.
            camera_id: Which camera this detection came from.
            local_track_id: Track ID within that camera.

        Returns:
            Global vehicle ID.
        """
        if feature is None or np.all(feature == 0):
            return self._register_new(feature, camera_id, local_track_id)

        best_match_id = None
        best_similarity = 0.0

        for gid, stored_feature in self.gallery.items():
            sim = 1.0 - cosine(feature, stored_feature)
            if sim > best_similarity:
                best_similarity = sim
                best_match_id = gid

        if best_similarity >= self.threshold and best_match_id is not None:
            # Update stored feature with exponential moving average
            self.gallery[best_match_id] = (
                0.8 * self.gallery[best_match_id] + 0.2 * feature
            )
            # Re-normalize
            norm = np.linalg.norm(self.gallery[best_match_id])
            if norm > 0:
                self.gallery[best_match_id] /= norm

            self.match_log.append({
                "global_id": best_match_id,
                "camera": camera_id,
                "local_track": local_track_id,
                "similarity": best_similarity,
                "action": "matched",
            })
            return best_match_id
        else:
            return self._register_new(feature, camera_id, local_track_id)

    def _register_new(self, feature: np.ndarray, camera_id: str,
                      local_track_id: int) -> int:
        new_id = self.next_id
        self.next_id += 1
        if feature is not None and not np.all(feature == 0):
            self.gallery[new_id] = feature.copy()

        self.match_log.append({
            "global_id": new_id,
            "camera": camera_id,
            "local_track": local_track_id,
            "similarity": 0.0,
            "action": "registered",
        })
        return new_id

    def get_gallery_size(self) -> int:
        return len(self.gallery)

    def reset(self):
        self.gallery.clear()
        self.next_id = 0
        self.match_log.clear()
