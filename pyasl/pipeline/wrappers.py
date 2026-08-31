from typing import Callable, Dict, Any
import time
import traceback


def run_wrapper(func: Callable) -> Callable:
    """Wrap a function so it accepts a single payload dict and returns the standardized contract."""

    def _wrapped(payload: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        try:
            inputs = payload.get("inputs", {})
            config = payload.get("config", {})
            metadata = payload.get("metadata", {})

            # call function with either (inputs, config) or payload
            try:
                res = func(inputs, config, metadata)
            except TypeError:
                # fallback to single-arg payload
                res = func(payload)

            if isinstance(res, dict):
                out = res
            else:
                out = {"status": "success", "outputs": res}

            out.setdefault("status", "success")
            out.setdefault("outputs", {})
            out["execution_time"] = time.time() - start
            return out
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "traceback": traceback.format_exc()}

    return _wrapped
