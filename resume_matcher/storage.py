"""File storage: local filesystem now, swap to S3 later.

Interface:
    save(category, file_id, data) -> path
    load(category, file_id) -> bytes
    delete(category, file_id) -> None
    get_path(category, file_id) -> str
"""

from __future__ import annotations

import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


class FileStorage:
    """Local file storage with S3-compatible interface.

    Categories:
        "uploads"  — original .docx files uploaded by the user
        "outputs"  — generated/optimized .docx files
    """

    def __init__(self, base_dir: str = DATA_DIR):
        self.base_dir = base_dir

    def _ensure_dir(self, category: str) -> str:
        path = os.path.join(self.base_dir, category)
        os.makedirs(path, exist_ok=True)
        return path

    def save(self, category: str, file_id: str, data: bytes, ext: str = ".docx") -> str:
        """Save a file and return its relative path.

        Args:
            category: "uploads" or "outputs"
            file_id: unique identifier (e.g. resume_id)
            data: raw file bytes
            ext: file extension

        Returns:
            Relative path from base_dir (e.g. "uploads/abc123.docx")
        """
        dir_path = self._ensure_dir(category)
        filename = f"{file_id}{ext}"
        full_path = os.path.join(dir_path, filename)
        with open(full_path, "wb") as f:
            f.write(data)
        return os.path.join(category, filename)

    def load(self, category: str, file_id: str, ext: str = ".docx") -> bytes:
        """Load a file by ID.

        Raises:
            FileNotFoundError: if the file does not exist.
        """
        filename = f"{file_id}{ext}"
        full_path = os.path.join(self.base_dir, category, filename)
        with open(full_path, "rb") as f:
            return f.read()

    def get_full_path(self, category: str, file_id: str, ext: str = ".docx") -> str:
        """Get absolute path to a stored file."""
        filename = f"{file_id}{ext}"
        return os.path.join(self.base_dir, category, filename)

    def exists(self, category: str, file_id: str, ext: str = ".docx") -> bool:
        """Check if a file exists in storage."""
        filename = f"{file_id}{ext}"
        return os.path.exists(os.path.join(self.base_dir, category, filename))

    def delete(self, category: str, file_id: str, ext: str = ".docx") -> None:
        """Delete a file from storage (no error if missing)."""
        filename = f"{file_id}{ext}"
        full_path = os.path.join(self.base_dir, category, filename)
        if os.path.exists(full_path):
            os.remove(full_path)
