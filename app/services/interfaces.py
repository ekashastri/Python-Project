"""
Service layer interfaces for OCR capabilities.
"""
from typing import Protocol, Optional
import numpy as np

class IOCRProvider(Protocol):
    """Abstraction for Optical Character Recognition services."""
    def extract_text(self, image: np.ndarray, cancel_check=None, status_callback=None) -> tuple[str, float]:
        ...

