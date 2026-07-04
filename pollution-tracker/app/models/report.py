"""
Core data models.

Two tables:
- Cluster: A group of reports referring to the same real-world incident.
- Report: A single citizen submission belonging to one cluster.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Enum,
    ForeignKey,
    Text,
    Integer,
    Boolean,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


def _uuid():
    """Generate a UUID for primary keys."""
    return uuid.uuid4()


def _now():
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------

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
    not_submitted = "not_submitted"
    pending_review = "pending_review"
    verified = "verified"
    not_verified = "not_verified"


# ---------------------------------------------------------------------
# CLUSTER MODEL
# ---------------------------------------------------------------------

class Cluster(Base):
    """
    Represents one real-world pollution incident.
    Multiple reports can belong to the same cluster.
    """

    __tablename__ = "clusters"

    __table_args__ = (
        CheckConstraint(
            "verification_confidence >= 0 AND verification_confidence <= 1",
            name="check_verification_confidence",
        ),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid,
    )

    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)

    category = Column(
        Enum(IssueCategory),
        nullable=False,
        index=True,
    )

    # Typical range: 0–100
    severity_score = Column(
        Integer,
        nullable=False,
        default=0,
    )

    status = Column(
        Enum(ReportStatus),
        nullable=False,
        default=ReportStatus.pending,
        index=True,
    )

    assigned_department = Column(
        String,
        nullable=True,
    )

    verification_status = Column(
        Enum(VerificationStatus),
        nullable=False,
        default=VerificationStatus.not_submitted,
        index=True,
    )

    verification_confidence = Column(
        Float,
        nullable=True,
    )

    municipal_summary = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        index=True,
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
    )

    reports = relationship(
        "Report",
        back_populates="cluster",
        cascade="all, delete-orphan",
    )

    @property
    def report_count(self):
        """Return number of reports in this cluster."""
        return len(self.reports)

    def __repr__(self):
        return (
            f"<Cluster(id={self.id}, "
            f"category={self.category.value}, "
            f"severity={self.severity_score})>"
        )


# ---------------------------------------------------------------------
# REPORT MODEL
# ---------------------------------------------------------------------

class Report(Base):
    """
    A single citizen submission.
    """

    __tablename__ = "reports"

    __table_args__ = (
        CheckConstraint(
            "ai_confidence >= 0 AND ai_confidence <= 1",
            name="check_ai_confidence",
        ),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid,
    )

    cluster_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "clusters.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    photo_path = Column(
        String,
        nullable=False,
    )

    after_photo_path = Column(
        String,
        nullable=True,
    )

    latitude = Column(
        Float,
        nullable=False,
        index=True,
    )

    longitude = Column(
        Float,
        nullable=False,
        index=True,
    )

    description = Column(
        Text,
        nullable=True,
    )

    category = Column(
        Enum(IssueCategory),
        nullable=False,
        index=True,
    )

    ai_confidence = Column(
        Float,
        nullable=True,
    )

    # Useful during hackathon debugging.
    ai_raw_response = Column(
        Text,
        nullable=True,
    )

    is_duplicate_of_cluster = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        index=True,
    )

    cluster = relationship(
        "Cluster",
        back_populates="reports",
    )

    def __repr__(self):
        return (
            f"<Report(id={self.id}, "
            f"category={self.category.value}, "
            f"cluster={self.cluster_id})>"
        )
