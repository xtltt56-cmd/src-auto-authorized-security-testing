from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from .controls import BudgetGovernor


@dataclass(frozen=True)
class Route:
    lane: str
    provider: str
    model: str
    estimated_cost: float


class ModelRouter:
    """Configurable lanes with a local deterministic fallback and no implicit API calls."""

    def __init__(self, config: Optional[Mapping[str, Any]] = None):
        config = config or {}
        self.default_lane = str(config.get("default_lane", "primary"))
        self.lanes = dict(config.get("lanes", {}))

    def route(self, task: str, complexity: str = "normal") -> Route:
        lane = "expert" if complexity == "high" else ("bulk" if complexity == "low" else self.default_lane)
        lane_cfg = self.lanes.get(lane, {})
        return Route(
            lane=lane,
            provider=str(lane_cfg.get("provider", "local")),
            model=str(lane_cfg.get("model", "heuristic-v1")),
            estimated_cost=float(lane_cfg.get("estimated_cost", 0.0)),
        )


class AITriage:
    def __init__(self, router: Optional[ModelRouter] = None, budget: Optional[BudgetGovernor] = None):
        self.router = router or ModelRouter()
        self.budget = budget

    def classify(self, finding: Mapping[str, Any]) -> Dict[str, Any]:
        severity = str(finding.get("severity", "info")).lower()
        evidence = str(finding.get("evidence", ""))
        route = self.router.route("triage", "high" if severity in ("high", "critical") else "normal")
        if self.budget is not None and route.estimated_cost:
            if not self.budget.can_spend(route.estimated_cost):
                return {"disposition": "manual_review", "confidence": 0.0, "reason": "budget_limit_exceeded", "route": route.__dict__}
            self.budget.record(route.estimated_cost, "ai_triage")
        if severity in ("high", "critical"):
            disposition = "needs_manual_validation"
            confidence = 0.72
        elif evidence:
            disposition = "candidate"
            confidence = 0.62
        else:
            disposition = "needs_manual_validation"
            confidence = 0.35
        return {
            "disposition": disposition,
            "confidence": confidence,
            "reason": "deterministic_local_triage",
            "route": route.__dict__,
        }
