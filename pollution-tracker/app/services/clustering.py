"""
Duplicate/cluster detection. Deliberately simple: geo-distance (haversine)
+ time window, no external geospatial library. This is cheap to build and
is one of the strongest "we understand government pain points" features
in the whole system, so it's worth getting right, but it does NOT need
PostGIS or anything heavyweight for hackathon scale.

If your city-scale data grows past a few thousand reports, look at
PostGIS's ST_DWithin instead — but don't build that under time pressure
this week.
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.report import Cluster, IssueCategory


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

    Note: this does a full scan of recent clusters. Fine for hackathon
    scale (hundreds to low thousands of clusters). If this ever needs to
    scale further, add a bounding-box pre-filter before the haversine
    check, or move to PostGIS.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.CLUSTER_TIME_WINDOW_HOURS)

    candidate_clusters = (
        db.query(Cluster)
        .filter(Cluster.category == category)
        .filter(Cluster.updated_at >= cutoff)
        .all()
    )

    for cluster in candidate_clusters:
        distance = _haversine_meters(latitude, longitude, cluster.latitude, cluster.longitude)
        if distance <= settings.CLUSTER_RADIUS_METERS:
            return cluster

    return None


def recompute_cluster_centroid(cluster: Cluster) -> None:
    """
    Recalculates the cluster's lat/lng as the average of all its reports'
    coordinates. Call this after adding a new report to a cluster.
    """
    if not cluster.reports:
        return
    cluster.latitude = sum(r.latitude for r in cluster.reports) / len(cluster.reports)
    cluster.longitude = sum(r.longitude for r in cluster.reports) / len(cluster.reports)
