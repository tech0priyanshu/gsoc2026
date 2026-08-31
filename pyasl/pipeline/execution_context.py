from typing import Dict, Any


class ExecutionContext:
    """Shared storage for pipeline execution (artifact passing, metadata)."""

    def __init__(self) -> None:
        self.storage: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.storage[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.storage.get(key, default)
