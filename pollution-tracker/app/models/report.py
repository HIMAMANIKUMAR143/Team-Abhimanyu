"""
Core data models.

Two tables:
- Cluster: a group of reports that are likely the same real-world incident
  (same location + time window). This is what powers duplicate detection.
- Report: a single citizen submission. Belongs to exactly one cluster.

If you need to add a field (e.g. a new report status), add it to the
relevant enum or column here, then run a migration (see README in this
folder for the Alembic command).
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Float, DateTime, Enum, ForeignKey, Text, Integer, Boolean
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IssueCategory(str, enum.Enum):
    garbage = "garbage"
    water_pollution = "water_pollution"
    air_pollution = "air_pollution"
    industrial_waste = "industrial_waste"
    sewage = "sewage"
    other = "other"


class ReportStatus(str, enum.Enum):
    pending = "pending"
    assigned = "assigned"
    resolved = "resolved"


class VerificationStatus(str, enum.Enum):
    not_submitted = "not_submitted"   # no after-photo yet
    pending_review = "pending_review"  # after-photo submitted, Gemini comparison ran
    verified = "verified"
    not_verified = "not_verified"


class Cluster(Base):
    """
    A cluster represents one real-world incident. Multiple reports can
    point to the same cluster if they're within CLUSTER_RADIUS_METERS and
    CLUSTER_TIME_WINDOW_HOURS of an existing report in that cluster.
    """
    __tablename__ = "clusters"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    # Centroid location, recalculated as new reports join the cluster.
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    category = Column(Enum(IssueCategory), nullable=False)

    severity_score = Column(Integer, nullable=False, default=0)
    status = Column(Enum(ReportStatus), nullable=False, default=ReportStatus.pending)
    assigned_department = Column(String, nullable=True)

    verification_status = Column(
        Enum(VerificationStatus), nullable=False, default=VerificationStatus.not_submitted
    )
    verification_confidence = Column(Float, nullable=True)  # 0.0 - 1.0
    municipal_summary = Column(Text, nullable=True)  # Gemini-generated report paragraph

    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    reports = relationship("Report", back_populates="cluster", cascade="all, delete-orphan")

    @property
    def report_count(self) -> int:
        return len(self.reports)


class Report(Base):
    """
    A single citizen submission. photo_path points to where the uploaded
    image is stored on disk (see app/services/storage.py).
    """
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    cluster_id = Column(UUID(as_uuid=False), ForeignKey("clusters.id"), nullable=False)

    photo_path = Column(String, nullable=False)
    after_photo_path = Column(String, nullable=True)  # before/after verification

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    description = Column(Text, nullable=True)

    category = Column(Enum(IssueCategory), nullable=False)
    ai_confidence = Column(Float, nullable=True)  # Gemini's confidence in the classification
    ai_raw_response = Column(Text, nullable=True)  # stored for debugging during the hackathon

    is_duplicate_of_cluster = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), default=_now)

    cluster = relationship("Cluster", back_populates="reports")
