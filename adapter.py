"""Small provider adapter contract for KERNEL integrations."""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ProviderAdapter:
    name: str
    capabilities: list[str] = field(default_factory=list)
    free_or_paid: str = "free"
    privacy_level: str = "configured"
    availability: str = "unknown"
    limits: dict[str, Any] = field(default_factory=dict)
    executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def estimate(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"provider": self.name, "cost_estimate": 0 if self.free_or_paid == "free" else task.get("max_spend", 0)}

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        if self.executor is None:
            return {"status": "unavailable", "error": f"No executor configured for {self.name}"}
        return self.executor(task)

    def health(self) -> dict[str, Any]:
        return {"name": self.name, "availability": self.availability, "limits": self.limits}
