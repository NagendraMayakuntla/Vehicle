"""Vehicle re-identification feature extractor for cross-camera matching."""

from typing import Tuple

import numpy as np
import cv2
import torch
import torch.nn as nn
from torchvision import transforms, models


class ReIDExtractor:
    """Extracts appearance feature vectors from detected vehicle crops.

    Uses a lightweight MobileNetV3 backbone fine-tuned for vehicle
    appearance features. Produces 512-dim feature vectors for matching.
    """

    def __init__(self, device: str = "auto"):
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # Use MobileNetV3-Small as a lightweight feature extractor
        backbone = models.mobilenet_v3_small(weights="DEFAULT")
        # Remove classifier, keep feature extractor
        self.model = nn.Sequential(
            backbone.features,
            backbone.avgpool,
            nn.Flatten(),
            nn.Linear(576, 512),  # Project to 512-dim
        ).to(self.device)
        self.model.eval()

        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((128, 128)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])

    def extract(self, frame: np.ndarray,
                bbox: Tuple[float, float, float, float]) -> np.ndarray:
        """Extract feature vector from a vehicle crop.

        Args:
            frame: Full BGR frame.
            bbox: Bounding box (x1, y1, x2, y2).

        Returns:
            512-dimensional normalized feature vector.
        """
        x1, y1, x2, y2 = map(int, bbox)

        # Clamp to frame bounds
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return np.zeros(512, dtype=np.float32)

        crop = frame[y1:y2, x1:x2]
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

        tensor = self.transform(crop_rgb).unsqueeze(0).to(self.device)

        with torch.no_grad():
            features = self.model(tensor)

        # L2 normalize
        features = features / (features.norm(dim=1, keepdim=True) + 1e-8)

        return features.cpu().numpy().flatten()
