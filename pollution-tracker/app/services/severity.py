from app.core.config import settings
from app.models.report import Cluster, IssueCategory

def compute_severity(cluster: Cluster) -> int:
    """
    Computes and returns the severity score for a cluster. Does NOT save
    it — caller is responsible for assigning it to cluster.severity_score
    and committing.
    """
    # Safely handle both Enum objects and raw strings depending on DB dialect
    category_val = (
        cluster.category.value 
        if hasattr(cluster.category, "value") 
        else cluster.category
    )
    
    base = settings.SEVERITY_BASE_WEIGHTS.get(category_val, 25)
    score = base

    # Safely extract the count. If report_count isn't a defined column property,
    # safely fall back to the length of the reports list (if loaded).
    report_count = getattr(cluster, "report_count", None)
    if report_count is None:
        report_count = len(cluster.reports) if getattr(cluster, "reports", None) else 0

    if report_count >= settings.SEVERITY_DUPLICATE_THRESHOLD:
        score += settings.SEVERITY_DUPLICATE_BONUS

    # TODO (Tier 2, only if Day 3 checkpoint is solid): sensitive-zone bonus.
    # Needs a dataset of school/hospital coordinates for your target city.
    # Once you have one, check distance from cluster.latitude/longitude to
    # the nearest sensitive zone and add settings.SEVERITY_SENSITIVE_ZONE_BONUS
    # if within e.g. 200m. 
    # 
    # Implementation hint:
    # from app.services.clustering import _haversine_meters
    # if any(_haversine_meters(cluster.latitude, cluster.longitude, z.lat, z.lon) <= 200 for z in sensitive_zones):
    #     score += settings.SEVERITY_SENSITIVE_ZONE_BONUS

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
    """Returns the assigned department for a given issue category."""
    return _DEPARTMENT_ROUTING.get(category, "General Municipal Office")
