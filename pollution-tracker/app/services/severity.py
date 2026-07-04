"""
Severity scoring. Kept to a small number of explainable variables on
purpose: base severity by issue type, plus a bonus if 3+ reports confirm
the same cluster. This is meant to be describable in one sentence during
judge Q&A: "issue type score, plus 10 if 3+ reports confirm it."

A sensitive-zone bonus (school/hospital proximity) is scaffolded but
disabled by default since it needs a zones dataset you may not have yet —
see the TODO below.
"""
from app.core.config import settings
from app.models.report import Cluster, IssueCategory


def compute_severity(cluster: Cluster) -> int:
    """
    Computes and returns the severity score for a cluster. Does NOT save
    it — caller is responsible for assigning it to cluster.severity_score
    and committing.
    """
    base = settings.SEVERITY_BASE_WEIGHTS.get(cluster.category.value, 25)

    score = base

    if cluster.report_count >= settings.SEVERITY_DUPLICATE_THRESHOLD:
        score += settings.SEVERITY_DUPLICATE_BONUS

    # TODO (Tier 2, only if Day 3 checkpoint is solid): sensitive-zone bonus.
    # Needs a dataset of school/hospital coordinates for your target city.
    # Once you have one, check distance from cluster.latitude/longitude to
    # the nearest sensitive zone and add settings.SEVERITY_SENSITIVE_ZONE_BONUS
    # if within e.g. 200m. Uses the same _haversine_meters helper from
    # clustering.py — don't duplicate that function, import it.

    return min(score, 100)  # cap at 100 so the dashboard sort/display stays sane


# Simple department routing lookup — near-free to maintain, as planned.
_DEPARTMENT_ROUTING = {
    IssueCategory.garbage: "Solid Waste Management",
    IssueCategory.water_pollution: "Water Board",
    IssueCategory.air_pollution: "Pollution Control Board",
    IssueCategory.industrial_waste: "Pollution Control Board",
    IssueCategory.sewage: "Sewerage Board",
    IssueCategory.other: "General Municipal Office",
}


def route_department(category: IssueCategory) -> str:
    return _DEPARTMENT_ROUTING.get(category, "General Municipal Office")
