import logging
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.report import Cluster, Report, VerificationStatus
from app.schemas.report import ClusterOut
from app.services import storage
from app.services.verification import verify_before_after

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/verification", tags=["verification"])


@router.post("/clusters/{cluster_id}/verify", response_model=ClusterOut)
def submit_after_photo(
    cluster_id: UUID,
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

    # OPTIMIZATION: Query the database directly for the oldest report 
    # instead of loading all reports into Python memory and using min()
    original_report = (
        db.query(Report)
        .filter(Report.cluster_id == cluster_id)
        .order_by(Report.created_at.asc())
        .first()
    )

    if not original_report:
        raise HTTPException(
            status_code=422, 
            detail="Cluster has no reports to compare against"
        )

    # Use synchronous read since we are inside a standard def
    after_bytes = after_photo.file.read()
    if not after_bytes:
        raise HTTPException(status_code=422, detail="Empty photo upload")

    after_photo_path = storage.save_photo(
        after_bytes, 
        after_photo.filename or "after.jpg"
    )
    original_report.after_photo_path = after_photo_path

    # Safely handle the external/AI verification call
    try:
        before_bytes = storage.read_photo(original_report.photo_path)
        result = verify_before_after(before_bytes, after_bytes)
    except Exception:
        logger.exception("Verification service failed")
        if hasattr(storage, "delete_photo"):
            storage.delete_photo(after_photo_path)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification service unavailable."
        )

    cluster.verification_status = result.verification_status
    cluster.verification_confidence = result.confidence

    if result.verification_status == VerificationStatus.verified:
        logger.info(
            "Cluster %s verified as resolved (confidence=%.2f)", 
            cluster_id, 
            result.confidence
        )

    # Safely commit to the database
    try:
        db.commit()
        db.refresh(cluster)
    except Exception:
        db.rollback()
        logger.exception("Failed to update cluster verification status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save verification results."
        )

    return cluster
