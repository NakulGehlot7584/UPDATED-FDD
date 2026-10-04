"""
Dependency injection provider for application-level singletons.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.datasets.manager import DatasetManager

# Application-level singleton DatasetManager instance
_dataset_manager = DatasetManager()

# Storage directory for uploaded files (configurable via OPENFDD_UPLOAD_DIR)
env_upload = os.getenv("OPENFDD_UPLOAD_DIR")
if env_upload:
    UPLOAD_DIR = Path(env_upload).resolve()
else:
    UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_dataset_manager() -> DatasetManager:
    """
    Provide the application-level DatasetManager instance.
    """
    return _dataset_manager
