"""
Core report endpoints: citizen upload, listing for the dashboard, and
status updates. This is the Day 1-2 loop from the roadmap:
upload -> classify -> score -> cluster -> show on dashboard -> update status.

Frontend team: build against these routes and the schemas in
app/schemas/report.py. That file IS the contract — if you need a field
that's not there, ask before assuming it exists.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.report import Cluster, Report, ReportStatus
from app.schemas.report import ClusterOut, ClusterStatusUpdate, ReportOut
from app.services import storage
from app.services.classifier import classify_image
from app.services.clustering import find_matching_cluster, recompute_cluster_centroid
from app.services.severity import compute_severity, route_department

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(
    latitude: float = Form(...),
    longitude: float = Form(...),
    description: Optional[str] = Form(None),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Citizen upload endpoint. Multipart form: latitude, longitude,
    description (optional), photo (file).

    Pipeline: save photo -> classify with Gemini (or mock) -> find or
    create matching cluster -> recompute severity -> return the report.
    """
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise HTTPException(status_code=422, detail="Invalid latitude/longitude")

    # Guards against non-image uploads (e.g. a .txt or .pdf) sailing
    # straight through to classify_image()/Gemini. Browsers/clients set
    # content_type from the file's extension or sniffed type, so this
    # isn't bulletproof against a deliberately relabeled file, but it
    # catches the honest-mistake case cheaply before we spend a
    # classification call on it.
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="File must be an image")

    photo_bytes = await photo.read()
    if not photo_bytes:
        raise HTTPException(status_code=422, detail="Empty photo upload")

    photo_path = storage.save_photo(photo_bytes, photo.filename or "upload.jpg")

    classification = classify_image(photo_bytes)

    cluster = find_matching_cluster(db, latitude, longitude, classification.category)
    if cluster is None:
        cluster = Cluster(
            latitude=latitude,
            longitude=longitude,
            category=classification.category,
            status=ReportStatus.pending,
            assigned_department=route_department(classification.category),
        )
        db.add(cluster)
        db.flush()  # get cluster.id before creating the report

    report = Report(
        cluster_id=cluster.id,
        photo_path=photo_path,
        latitude=latitude,
        longitude=longitude,
        description=description,
        category=classification.category,
        ai_confidence=classification.confidence,
        ai_raw_response=classification.raw_response,
        is_duplicate_of_cluster=(len(cluster.reports) > 0),
    )
    db.add(report)
    db.flush()

    # IMPORTANT: cluster.reports may be stale here — if `cluster` was
    # fetched by find_matching_cluster() rather than just created above,
    # SQLAlchemy has no reason to know the report we just flushed belongs
    # to it yet, since we set cluster_id directly rather than appending
    # through the relationship. Expire the cached collection so the next
    # access re-queries the DB and reflects the true current count.
    # Bug caught during real-Postgres testing on 2026-07-04 — see if you
    # hit something similar when adding new relationship-touching code.
    db.expire(cluster, ["reports"])

    recompute_cluster_centroid(cluster)
    cluster.severity_score = compute_severity(cluster)

    db.commit()
    db.refresh(report)

    logger.info(
        "Report %s created in cluster %s (category=%s, severity=%d, reports_in_cluster=%d)",
        report.id, cluster.id, cluster.category.value, cluster.severity_score, cluster.report_count,
    )

    return report


@router.get("/clusters", response_model=List[ClusterOut])
def list_clusters(
    status: Optional[ReportStatus] = None,
    db: Session = Depends(get_db),
):
    """
    Dashboard endpoint: returns clusters (not raw reports), ranked by
    severity descending. This is what the admin map + table should call.
    """
    query = db.query(Cluster)
    if status is not None:
        query = query.filter(Cluster.status == status)

    clusters = query.order_by(Cluster.severity_score.desc()).all()
    return clusters


@router.get("/clusters/{cluster_id}", response_model=ClusterOut)
def get_cluster(cluster_id: str, db: Session = Depends(get_db)):
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return cluster


@router.get("/clusters/{cluster_id}/reports", response_model=List[ReportOut])
def get_cluster_reports(cluster_id: str, db: Session = Depends(get_db)):
    """Returns all individual reports that make up a cluster."""
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return cluster.reports


@router.patch("/clusters/{cluster_id}/status", response_model=ClusterOut)
def update_cluster_status(
    cluster_id: str,
    update: ClusterStatusUpdate,
    db: Session = Depends(get_db),
):
    """Admin dashboard status update: Pending -> Assigned -> Resolved."""
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")

    cluster.status = update.status
    db.commit()
    db.refresh(cluster)
    return cluster