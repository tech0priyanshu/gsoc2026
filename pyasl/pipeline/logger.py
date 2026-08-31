import json
from typing import Any, Dict
from datetime import datetime


def node_log(entry: Dict[str, Any]) -> str:
    e = {**entry}
    e.setdefault("timestamp", datetime.utcnow().isoformat())
    return json.dumps(e)


def pipeline_log(entry: Dict[str, Any]) -> str:
    e = {**entry}
    e.setdefault("timestamp", datetime.utcnow().isoformat())
    return json.dumps(e)
