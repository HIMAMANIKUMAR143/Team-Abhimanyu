from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.models.report import IssueCategory, ReportStatus, VerificationStatus


# ---------- Report ----------

class ReportCreate(BaseModel):
    """
    What the citizen upload form sends. The photo itself is sent as
    multipart/form-data (see the router), not in this JSON body — this
    schema covers the accompanying fields.
    """
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    description: Optional[str] = None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cluster_id: UUID
    photo_path: str
    after_photo_path: Optional[str] = None
    latitude: float
    longitude: float
    description: Optional[str] = None
    category: IssueCategory
    ai_confidence: Optional[float] = None
    is_duplicate_of_cluster: bool
    created_at: datetime


# ---------- Cluster (what the dashboard actually renders) ----------

class ClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    latitude: float
    longitude: float
    category: IssueCategory
    severity_score: int
    status: ReportStatus
    assigned_department: Optional[str] = None
    verification_status: VerificationStatus
    verification_confidence: Optional[float] = None
    municipal_summary: Optional[str] = None
    report_count: int
    created_at: datetime
    updated_at: datetime


class ClusterStatusUpdate(BaseModel):
    status: ReportStatus


# ---------- Verification (before/after) ----------

class VerificationResult(BaseModel):
    verification_status: VerificationStatus
    confidence: float
    explanation: str
