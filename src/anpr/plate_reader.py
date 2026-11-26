"""OCR-based number plate text reader using EasyOCR."""

import re
from typing import Optional, Tuple

import numpy as np


class PlateReader:
    """Reads text from number plate images using EasyOCR.

    Supports Indian vehicle number plate format: XX-00-XX-0000
    """

    # Indian plate format: State code (2 letters) + District (2 digits) + Series (1-2 letters) + Number (4 digits)
    INDIAN_PLATE_PATTERN = re.compile(
        r"^[A-Z]{2}\s*\d{1,2}\s*[A-Z]{1,3}\s*\d{1,4}$"
    )

    def __init__(self, languages: list = None, gpu: bool = False):
        import easyocr
        self.reader = easyocr.Reader(
            languages or ["en"],
            gpu=gpu,
        )

    def read_plate(self, plate_image: np.ndarray) -> Tuple[Optional[str], float]:
        """Read text from a preprocessed plate image.

        Args:
            plate_image: Preprocessed plate image (grayscale or BGR).

        Returns:
            Tuple of (plate_text, confidence). plate_text is None if no text detected.
        """
        results = self.reader.readtext(plate_image)

        if not results:
            return None, 0.0

        # Combine all detected text segments
        full_text = " ".join([r[1] for r in results])
        avg_confidence = sum(r[2] for r in results) / len(results)

        # Clean up the text
        cleaned = self._clean_plate_text(full_text)

        if cleaned:
            return cleaned, avg_confidence
        return full_text.upper().strip(), avg_confidence

    def _clean_plate_text(self, text: str) -> Optional[str]:
        """Clean and validate plate text to match Indian format."""
        # Remove special characters, keep letters and digits
        cleaned = re.sub(r"[^A-Za-z0-9]", "", text.upper())

        if len(cleaned) < 4:
            return None

        # Common OCR corrections for plates
        corrections = {
            "O": "0", "I": "1", "S": "5", "B": "8",
            "Z": "2", "G": "6", "T": "7",
        }

        # Try to format as Indian plate
        # First 2 chars should be letters (state code)
        if len(cleaned) >= 6:
            state = cleaned[:2]
            rest = cleaned[2:]

            # Correct digits in state code
            state = state.replace("0", "O").replace("1", "I").replace("5", "S")

            # Correct letters in number portions
            district = rest[:2]
            for old, new in corrections.items():
                district = district.replace(old, new)

            series_and_num = rest[2:]

            formatted = f"{state}{district}{series_and_num}"
            return formatted

        return cleaned

    def validate_indian_plate(self, plate_text: str) -> bool:
        """Check if text matches Indian vehicle number plate format."""
        if not plate_text:
            return False
        cleaned = re.sub(r"[\s-]", "", plate_text.upper())
        return bool(self.INDIAN_PLATE_PATTERN.match(cleaned))
