import logging
import os
from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.report import Cluster, Report, ReportStatus
from app.schemas.report import ClusterOut, ClusterStatusUpdate, ReportOut
from app.services import storage
from app.services.classifier import classify_image
from app.services.clustering import (
    find_matching_cluster,
    recompute_cluster_centroid,
)
from app.services.severity import (
    compute_severity,
    route_department,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


def get_cluster_or_404(
    db: Session,
    cluster_id: UUID,
) -> Cluster:
    cluster = (
        db.query(Cluster)
        .filter(Cluster.id == cluster_id)
        .first()
    )

    if cluster is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster not found",
        )

    return cluster


@router.post(
    "",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    latitude: float = Form(...),
    longitude: float = Form(...),
    description: Optional[str] = Form(None),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not (-90 <= latitude <= 90):
        raise HTTPException(422, "Invalid latitude")

    if not (-180 <= longitude <= 180):
        raise HTTPException(422, "Invalid longitude")

    if (
        not photo.content_type
        or not photo.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=422,
            detail="File must be an image",
        )

    extension = os.path.splitext(photo.filename or "")[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail="Unsupported image format",
        )

    # Use synchronous read since we are inside a standard def to prevent event loop blocking
    photo_bytes = photo.file.read()

    if not photo_bytes:
        raise HTTPException(
            status_code=422,
            detail="Empty photo upload",
        )

    if len(photo_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size exceeds 10 MB.",
        )

    photo_path = storage.save_photo(
        photo_bytes,
        photo.filename or "upload.jpg",
    )

    try:
        classification = classify_image(photo_bytes)

    except Exception:
        logger.exception("Image classification failed")

        if hasattr(storage, "delete_photo"):
            storage.delete_photo(photo_path)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Classification service unavailable.",
        )

    cluster = find_matching_cluster(
        db,
        latitude,
        longitude,
        classification.category,
    )

    is_new_cluster = False
    if cluster is None:
        is_new_cluster = True
        cluster = Cluster(
            latitude=latitude,
            longitude=longitude,
            category=classification.category,
            status=ReportStatus.pending,
            assigned_department=route_department(classification.category),
        )

        db.add(cluster)
        db.flush()

    report = Report(
        cluster_id=cluster.id,
        photo_path=photo_path,
        latitude=latitude,
        longitude=longitude,
        description=description,
        category=classification.category,
        ai_confidence=classification.confidence,
        ai_raw_response=classification.raw_response,
        # Determine duplication without lazy-loading all historical cluster reports
        is_duplicate_of_cluster=not is_new_cluster,
    )

    db.add(report)
    db.flush()

    db.expire(cluster, ["reports"])

    recompute_cluster_centroid(cluster)
    cluster.severity_score = compute_severity(cluster)

    try:
        db.commit()
        db.refresh(cluster)
        db.refresh(report)

    except Exception:
        db.rollback()
        logger.exception("Failed to create report")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save report.",
        )

    logger.info(
        "Report %s created in cluster %s "
        "(category=%s, severity=%d, reports=%d)",
        report.id,
        cluster.id,
        cluster.category.value,
        cluster.severity_score,
        getattr(cluster, "report_count", 0),  # Safely handle dynamic properties
    )

    return report


@router.get(
    "/clusters",
    response_model=List[ClusterOut],
)
def list_clusters(
    report_status: Optional[ReportStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """
    Returns clusters ordered by severity (highest first).
    Used by the admin dashboard.
    """
    query = db.query(Cluster)

    if report_status is not None:
        query = query.filter(Cluster.status == report_status)

    clusters = query.order_by(Cluster.severity_score.desc()).all()

    return clusters


@router.get(
    "/clusters/{cluster_id}",
    response_model=ClusterOut,
)
def get_cluster(
    cluster_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get a single cluster by ID.
    """
    return get_cluster_or_404(db, cluster_id)


@router.get(
    "/clusters/{cluster_id}/reports",
    response_model=List[ReportOut],
)
def get_cluster_reports(
    cluster_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Returns all reports belonging to a cluster.
    """
    cluster = get_cluster_or_404(db, cluster_id)
    return cluster.reports


@router.patch(
    "/clusters/{cluster_id}/status",
    response_model=ClusterOut,
)
def update_cluster_status(
    cluster_id: UUID,
    update: ClusterStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    Update cluster status:
    Pending -> Assigned -> Resolved
    """
    cluster = get_cluster_or_404(db, cluster_id)
    cluster.status = update.status

    try:
        db.commit()
        db.refresh(cluster)

    except Exception:
        db.rollback()
        logger.exception("Failed to update cluster status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update cluster status.",
        )

    logger.info(
        "Cluster %s status updated to %s",
        cluster.id,
        cluster.status.value,
    )

    return cluster
