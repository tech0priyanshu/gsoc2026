from typing import Callable, Dict, Optional, Any, List
import importlib
import inspect
import logging
import threading

from pyasl.pipeline.exceptions.errors import AmbiguousStepName

logger = logging.getLogger("pyasl.pipeline.registry")

_local_context = threading.local()


def get_shared_context() -> dict:
    """Return thread-local shared context dictionary."""
    if not hasattr(_local_context, "ctx"):
        _local_context.ctx = {}
    return _local_context.ctx


def clear_shared_context() -> None:
    """Reset thread-local shared context dictionary."""
    _local_context.ctx = {}


class PreclinicalClassWrapper:
    """
    Wraps standard preclinical class modules (which have run(ctx, **p))
    into generic callables that accept a payload dictionary.
    """

    def __init__(self, cls_type: type, style: str = "kwargs", need_root: bool = False):
        self.cls_type = cls_type
        self.style = style
        self.need_root = need_root

    def __call__(self, payload: dict) -> dict:
        inst = self.cls_type()
        ctx = get_shared_context()

        config = payload.get("config", {}) or {}
        inputs = payload.get("inputs", {}) or {}
        params = {**config, **inputs}

        if self.need_root and "root" not in params and "root" in ctx:
            params["root"] = ctx["root"]

        # Ensure parameters are correctly formatted for preclinical scripts
        if hasattr(inst, "run"):
            if self.style == "kwargs":
                inst.run(ctx, **params)
            else:
                dict_params = {k: v for k, v in params.items() if k != "root"}
                inst.run(ctx, dict_params)

        return {"status": "success", "outputs": dict(ctx)}


def register_step(fn: Callable) -> Callable:
    """Decorator to mark a function or class as an explicit PyASL pipeline step."""
    setattr(fn, "_pyasl_step", True)
    return fn


class Registry:
    def __init__(self) -> None:
        self._registry: Dict[str, Callable] = {}
        # Fix 3B: Reverse index mapping short names to list of full keys
        self._short_name_index: Dict[str, List[str]] = {}

    def _add_to_index(self, key: str) -> None:
        short_name = key.rsplit(".", 1)[-1]
        if short_name not in self._short_name_index:
            self._short_name_index[short_name] = []
        if key not in self._short_name_index[short_name]:
            self._short_name_index[short_name].append(key)

    def register(self, name: Optional[str] = None):
        def _decorator(func: Callable):
            register_step(func)
            key = name or f"{func.__module__}.{func.__name__}"
            self._registry[key] = func
            self._add_to_index(key)
            return func

        if callable(name):
            # Used as @register without arguments
            func = name
            name = None
            return _decorator(func)

        return _decorator

    def _wrap_if_class(self, obj: Any, name: str) -> Callable:
        if isinstance(obj, type):
            style = "kwargs"
            need_root = False
            try:
                from pyasl.pipelines.custom_pipeline import _ALIAS, _normkey
                key = _normkey(name)
                if key in _ALIAS:
                    _, _, style, need_root = _ALIAS[key]
            except Exception as e:
                # Fix 3C: Log warning instead of silently swallowing import errors
                logger.warning("Failed to resolve alias for %s: %s", name, e)
            return PreclinicalClassWrapper(obj, style, need_root)
        return obj

    def get(self, name: str) -> Callable:
        # 1. Direct lookup
        if name in self._registry:
            return self._wrap_if_class(self._registry[name], name)

        # 2. Dynamic import: accept dotted path
        if "." in name:
            mod_name, func_name = name.rsplit(".", 1)
            try:
                mod = importlib.import_module(mod_name)
                func = getattr(mod, func_name)
                if callable(func):
                    self._registry[name] = func
                    self._add_to_index(name)
                    return self._wrap_if_class(func, name)
            except Exception:
                pass

        # 3. Fix 3B: Index lookup (O(1) short name index instead of linear scan)
        if name in self._short_name_index:
            matches = self._short_name_index[name]
            if len(matches) > 1:
                raise AmbiguousStepName(
                    f"Short step name '{name}' is ambiguous. Matching keys: {matches}"
                )
            if len(matches) == 1:
                full_key = matches[0]
                return self._wrap_if_class(self._registry[full_key], name)

        raise KeyError(f"Function {name} not found in registry")

    def list_registered(self) -> list:
        """Return a sorted list of all registered function names."""
        return sorted(self._registry.keys())

    def is_registered(self, name: str) -> bool:
        """Return True if `name` is in the registry (without dynamic import)."""
        if name in self._registry:
            return True
        if name in self._short_name_index and len(self._short_name_index[name]) == 1:
            return True
        return False

    def autodiscover(self, package: str) -> None:
        """Import modules under `package` and register decorated or step-matching callables."""
        import pkgutil

        try:
            pkg = importlib.import_module(package)
        except Exception:
            return

        if not hasattr(pkg, "__path__"):
            return

        for finder, modname, ispkg in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
            try:
                mod = importlib.import_module(modname)
            except Exception:
                continue
            for attr in dir(mod):
                if attr.startswith("_"):
                    continue
                obj = getattr(mod, attr)
                if callable(obj):
                    # Fix 3A: Only register objects decorated with @register (_pyasl_step)
                    # or matching naming conventions (PascalCase class or step_* function) defined in module
                    is_explicit_step = getattr(obj, "_pyasl_step", False)
                    obj_module = getattr(obj, "__module__", "")

                    # Naming convention: defined in this module & (PascalCase class or step_* function)
                    is_named_step = (
                        obj_module == modname and (
                            (inspect.isclass(obj) and attr[0].isupper()) or
                            attr.startswith("step_")
                        )
                    )

                    if is_explicit_step or is_named_step:
                        key = f"{modname}.{attr}"
                        if key not in self._registry:
                            self._registry[key] = obj
                            self._add_to_index(key)


registry = Registry()

# Always perform auto-discovery on startup/import
try:
    registry.autodiscover("pyasl.modules")
except Exception:
    pass


def register(name: Optional[str] = None):
    return registry.register(name)
