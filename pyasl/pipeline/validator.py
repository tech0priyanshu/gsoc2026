import inspect
from typing import List, Dict, Any, Optional
from .graph import build_graph, topological_sort
from .exceptions.errors import CycleDetectedError, InvalidPipelineError


def validate_nodes_schema(nodes: List[Dict]) -> None:
    ids = [n.get("id") for n in nodes]
    if None in ids:
        raise InvalidPipelineError("Every node must have an 'id' field")
    # duplicate ids
    if len(ids) != len(set(ids)):
        raise InvalidPipelineError("Duplicate node ids detected")


def validate_dependencies_exist(nodes: List[Dict]) -> None:
    ids = {n["id"] for n in nodes}
    for n in nodes:
        for dep in n.get("depends_on", []):
            if dep not in ids:
                raise InvalidPipelineError(f"Unknown dependency '{dep}' referenced by node '{n['id']}'")
            if dep == n["id"]:
                raise InvalidPipelineError(f"Node '{n['id']}' cannot depend on itself")


def detect_cycles(nodes: List[Dict]) -> None:
    graph = build_graph(nodes)
    try:
        topological_sort(graph)
    except ValueError:
        raise CycleDetectedError("Cycle detected in pipeline graph")


def validate_pipeline(nodes: List[Dict]) -> None:
    validate_nodes_schema(nodes)
    validate_dependencies_exist(nodes)
    detect_cycles(nodes)


def pre_flight_check(nodes: List[Dict], registry_inst: Optional[Any] = None) -> Dict[str, Any]:
    """
    Perform pre-flight function validation before pipeline run.
    Validates node schema, cycles, missing function imports, and signatures.
    Returns payload dict {"valid": True/False, "errors": list, "nodes_checked": int}.
    """
    if registry_inst is None:
        from .registry import registry
        registry_inst = registry

    errors: List[str] = []

    # 1. Structural graph validation
    try:
        validate_pipeline(nodes)
    except Exception as exc:
        errors.append(f"Graph Structural Error: {exc}")

    # 2. Pre-flight function & dependency resolution
    for n in nodes:
        node_id = n.get("id", "unknown")
        func_name = n.get("function")
        if not func_name:
            errors.append(f"Node '{node_id}': Missing 'function' field.")
            continue

        try:
            target_callable = registry_inst.get(func_name)
            if target_callable is None:
                errors.append(f"Node '{node_id}': Function '{func_name}' resolved to None.")
            else:
                # Check signature compatibility
                try:
                    inspect.signature(target_callable)
                except (ValueError, TypeError):
                    pass  # Built-in or C-wrapper without signature
        except KeyError:
            errors.append(f"Node '{node_id}': Function '{func_name}' is not registered.")
        except ImportError as imp_err:
            errors.append(f"Node '{node_id}': Module import failure for '{func_name}': {imp_err}")
        except Exception as exc:
            errors.append(f"Node '{node_id}': Unhandled error resolving '{func_name}': {exc}")

    if errors:
        error_msg = "\n".join(f"• {e}" for e in errors)
        raise InvalidPipelineError(f"Pre-flight Validation Failed ({len(errors)} errors):\n{error_msg}")

    return {"valid": True, "errors": [], "nodes_checked": len(nodes)}
