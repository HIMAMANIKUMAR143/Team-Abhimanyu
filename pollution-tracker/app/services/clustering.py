import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, object_session

from app.core.config import settings
from app.models.report import Cluster, IssueCategory, Report


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lng points, in meters."""
    R = 6_371_000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def find_matching_cluster(
    db: Session,
    latitude: float,
    longitude: float,
    category: IssueCategory,
) -> Optional[Cluster]:
    """
    Looks for an existing cluster of the SAME category within both the
    configured radius and time window. Returns None if no match, meaning
    the caller should create a new cluster.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.CLUSTER_TIME_WINDOW_HOURS)

    # OPTIMIZATION: Bounding Box Pre-filter
    # 1 degree of latitude is ~111,320 meters.
    # 1 degree of longitude varies by latitude: ~111,320 * cos(latitude)
    lat_offset = settings.CLUSTER_RADIUS_METERS / 111320.0
    lon_offset = settings.CLUSTER_RADIUS_METERS / (111320.0 * math.cos(math.radians(latitude)))

    candidate_clusters = (
        db.query(Cluster)
        .filter(
            Cluster.category == category,
            Cluster.updated_at >= cutoff,
            # Let the database aggressively filter out clusters that aren't even close
            Cluster.latitude.between(latitude - lat_offset, latitude + lat_offset),
            Cluster.longitude.between(longitude - lon_offset, longitude + lon_offset)
        )
        .all()
    )

    # Perform the exact Haversine check only on the small handful of nearby clusters
    for cluster in candidate_clusters:
        distance = _haversine_meters(latitude, longitude, cluster.latitude, cluster.longitude)
        if distance <= settings.CLUSTER_RADIUS_METERS:
            return cluster

    return None


def recompute_cluster_centroid(cluster: Cluster) -> None:
    """
    Recalculates the cluster's lat/lng as the average of all its reports'
    coordinates. Offloads the math to the database to avoid loading all 
    report objects into Python memory.
    """
    # Dynamically grab the active database session from the cluster object
    session = object_session(cluster)
    
    if not session:
        # Fallback to in-memory math if the cluster is detached from the DB
        if not getattr(cluster, "reports", None):
            return
        cluster.latitude = sum(r.latitude for r in cluster.reports) / len(cluster.reports)
        cluster.longitude = sum(r.longitude for r in cluster.reports) / len(cluster.reports)
        return

    # OPTIMIZATION: Ask the database to return only the calculated averages
    avg_coords = (
        session.query(
            func.avg(Report.latitude),
            func.avg(Report.longitude)
        )
        .filter(Report.cluster_id == cluster.id)
        .first()
    )

    if avg_coords and avg_coords[0] is not None:
        cluster.latitude = float(avg_coords[0])
        cluster.longitude = float(avg_coords[1])
