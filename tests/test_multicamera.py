"""Tests for multi-camera module."""

import pytest
import numpy as np

from src.multicamera.cross_camera_matcher import CrossCameraMatcher
from src.multicamera.global_count_tracker import GlobalCountTracker


class TestCrossCameraMatcher:
    def test_register_new_vehicle(self):
        matcher = CrossCameraMatcher(similarity_threshold=0.7)
        feature = np.random.randn(512).astype(np.float32)
        feature /= np.linalg.norm(feature)

        gid = matcher.match_or_register(feature, "cam_01", 1)
        assert gid == 0
        assert matcher.get_gallery_size() == 1

    def test_match_same_vehicle(self):
        matcher = CrossCameraMatcher(similarity_threshold=0.7)
        feature1 = np.random.randn(512).astype(np.float32)
        feature1 /= np.linalg.norm(feature1)

        # Register
        gid1 = matcher.match_or_register(feature1, "cam_01", 1)

        # Same feature from different camera should match
        feature2 = feature1 + np.random.randn(512).astype(np.float32) * 0.01
        feature2 /= np.linalg.norm(feature2)

        gid2 = matcher.match_or_register(feature2, "cam_02", 5)
        assert gid1 == gid2

    def test_different_vehicles_get_different_ids(self):
        matcher = CrossCameraMatcher(similarity_threshold=0.7)

        feat1 = np.random.randn(512).astype(np.float32)
        feat1 /= np.linalg.norm(feat1)

        feat2 = np.random.randn(512).astype(np.float32)
        feat2 /= np.linalg.norm(feat2)

        gid1 = matcher.match_or_register(feat1, "cam_01", 1)
        gid2 = matcher.match_or_register(feat2, "cam_01", 2)

        # Random features should be different enough to not match
        assert gid1 != gid2

    def test_reset(self):
        matcher = CrossCameraMatcher()
        feature = np.random.randn(512).astype(np.float32)
        matcher.match_or_register(feature, "cam_01", 1)
        matcher.reset()
        assert matcher.get_gallery_size() == 0


class TestGlobalCountTracker:
    def test_register_and_count(self):
        tracker = GlobalCountTracker()
        tracker.register(0, "car", "cam_01")
        tracker.register(1, "bus", "cam_01")
        tracker.register(2, "car", "cam_02")

        counts = tracker.get_total_counts()
        assert counts["car"] == 2
        assert counts["bus"] == 1
        assert counts["total"] == 3

    def test_deduplication(self):
        """Same global ID from different cameras should not double-count."""
        tracker = GlobalCountTracker()
        tracker.register(0, "car", "cam_01")
        tracker.register(0, "car", "cam_02")  # Same vehicle, different camera

        counts = tracker.get_total_counts()
        assert counts["car"] == 1  # Still 1, not 2

    def test_total_unique_vehicles(self):
        tracker = GlobalCountTracker()
        tracker.register(0, "car", "cam_01")
        tracker.register(1, "bus", "cam_01")
        tracker.register(0, "car", "cam_02")  # Duplicate

        assert tracker.get_total_unique_vehicles() == 2

    def test_reset(self):
        tracker = GlobalCountTracker()
        tracker.register(0, "car", "cam_01")
        tracker.reset()

        counts = tracker.get_total_counts()
        assert counts.get("total", 0) == 0
