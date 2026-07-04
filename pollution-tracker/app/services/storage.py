"""
Photo storage. Saves to local disk under /app/uploads (mounted as a
Docker volume so photos survive container restarts). This is intentionally
simple for hackathon scope — if you needed cloud storage (S3 etc.) later,
this is the only file you'd change.
"""
import uuid
from pathlib import Path

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def save_photo(file_bytes: bytes, original_filename: str) -> str:
    """
    Saves photo bytes to disk with a unique filename, returns the relative
    path to store in the database.
    """
    extension = Path(original_filename).suffix or ".jpg"
    unique_name = f"{uuid.uuid4()}{extension}"
    destination = UPLOAD_DIR / unique_name
    destination.write_bytes(file_bytes)
    return str(destination)


def read_photo(photo_path: str) -> bytes:
    """
    Reads a previously-saved photo back off disk.

    Raises FileNotFoundError with a clear message (rather than letting
    Path.read_bytes() throw its own less-obvious version of the same
    error) if the file is missing — e.g. the DB row survived a
    `docker compose down -v` that wiped the uploads volume, or the path
    stored on the report was ever wrong. Callers that hit this from a
    request (see routers/verification.py) should catch it and return a
    clean 404/409 instead of letting FastAPI turn it into a raw 500.
    """
    path = Path(photo_path)
    if not path.exists():
        raise FileNotFoundError(f"Photo not found on disk: {photo_path}")
    return path.read_bytes()