"""
Pydantic schemas — these define the exact JSON shape going in and out of
every endpoint. This IS the API contract. If frontend and backend both
build against this file, they won't drift apart.

Naming convention: `XCreate` for what the client sends to create X,
`XOut` for what the server sends back, `XUpdate` for partial updates.
"""
from datetime import datetime
from typing import Optional

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

    id: str
    cluster_id: str
    photo_path: str
    after_photo_path: Optional[str]
    latitude: float
    longitude: float
    description: Optional[str]
    category: IssueCategory
    ai_confidence: Optional[float]
    is_duplicate_of_cluster: bool
    created_at: datetime


# ---------- Cluster (what the dashboard actually renders) ----------

class ClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    latitude: float
    longitude: float
    category: IssueCategory
    severity_score: int
    status: ReportStatus
    assigned_department: Optional[str]
    verification_status: VerificationStatus
    verification_confidence: Optional[float]
    municipal_summary: Optional[str]
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
