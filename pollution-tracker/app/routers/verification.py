"""
Before/after verification endpoint — Day 3 differentiator feature.
Citizen or municipal worker submits a follow-up photo; Gemini (or mock)
compares it against the original and returns a verified/not-verified
confidence.
"""
import logging

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.report import Cluster, Report, VerificationStatus
from app.schemas.report import ClusterOut
from app.services import storage
from app.services.verification import verify_before_after

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/verification", tags=["verification"])


@router.post("/clusters/{cluster_id}/verify", response_model=ClusterOut)
async def submit_after_photo(
    cluster_id: str,
    after_photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Submits an "after" photo for a cluster. Compares it against the
    ORIGINAL report's photo (the first report in the cluster) and updates
    the cluster's verification status + confidence.
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if not cluster.reports:
        raise HTTPException(status_code=422, detail="Cluster has no reports to compare against")

    original_report = min(cluster.reports, key=lambda r: r.created_at)

    after_bytes = await after_photo.read()
    if not after_bytes:
        raise HTTPException(status_code=422, detail="Empty photo upload")

    after_photo_path = storage.save_photo(after_bytes, after_photo.filename or "after.jpg")
    original_report.after_photo_path = after_photo_path

    before_bytes = storage.read_photo(original_report.photo_path)
    result = verify_before_after(before_bytes, after_bytes)

    cluster.verification_status = result.verification_status
    cluster.verification_confidence = result.confidence

    if result.verification_status == VerificationStatus.verified:
        logger.info("Cluster %s verified as resolved (confidence=%.2f)", cluster_id, result.confidence)

    db.commit()
    db.refresh(cluster)
    return cluster
