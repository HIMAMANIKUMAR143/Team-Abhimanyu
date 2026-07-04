import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Ensure uploads directory exists on startup
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def save_photo(file_bytes: bytes, original_filename: str) -> str:
    """
    Saves photo bytes to disk with a unique filename, returns the relative
    path to store in the database.
    """
    extension = Path(original_filename).suffix or ".jpg"
    unique_name = f"{uuid.uuid4()}{extension}"
    destination = UPLOAD_DIR / unique_name
    
    destination.write_bytes(file_bytes)
    
    # Return posix path (forward slashes) so DB paths are consistent 
    # regardless of the host OS developing the app
    return destination.as_posix()


def _ensure_safe_path(photo_path: str) -> Path:
    """
    Internal helper to prevent Path Traversal attacks.
    Ensures the requested path is actually inside the UPLOAD_DIR.
    """
    target_path = Path(photo_path).resolve()
    base_path = UPLOAD_DIR.resolve()
    
    if not target_path.is_relative_to(base_path):
        logger.error("Security warning: Attempted path traversal -> %s", photo_path)
        raise ValueError("Invalid file path requested.")
        
    return target_path


def read_photo(photo_path: str) -> bytes:
    """
    Reads a previously-saved photo back off disk.
    Includes path traversal protection.
    """
    path = _ensure_safe_path(photo_path)
    
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Photo not found on disk: {photo_path}")
        
    return path.read_bytes()


def delete_photo(photo_path: str) -> None:
    """
    Deletes a photo from disk. Used for cleanup if a downstream service 
    (like AI classification) fails after the image is saved.
    """
    try:
        path = _ensure_safe_path(photo_path)
        if path.exists() and path.is_file():
            path.unlink()
            logger.info("Deleted orphaned photo at %s", photo_path)
    except Exception as e:
        # We don't want cleanup failures to crash the main application thread
        logger.warning("Failed to delete photo at %s: %s", photo_path, str(e))
