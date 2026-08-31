from typing import Dict, List, Set


def build_graph(nodes: List[dict]) -> Dict[str, List[str]]:
    """Build adjacency mapping parent->children from node definitions.

    nodes: list of Node-like dicts with keys 'id' and optional 'depends_on'
    """
    graph = {n["id"]: [] for n in nodes}
    for n in nodes:
        nid = n["id"]
        for parent in n.get("depends_on", []):
            if parent not in graph:
                graph[parent] = []
            graph[parent].append(nid)
    return graph


def topological_sort(graph: Dict[str, List[str]]) -> List[str]:
    """Return topological order using Kahn's algorithm."""
    # compute in-degree
    in_deg = {u: 0 for u in graph}
    for u in graph:
        for v in graph[u]:
            in_deg[v] = in_deg.get(v, 0) + 1

    queue = [u for u, deg in in_deg.items() if deg == 0]
    order: List[str] = []
    while queue:
        u = queue.pop(0)
        order.append(u)
        for v in graph.get(u, []):
            in_deg[v] -= 1
            if in_deg[v] == 0:
                queue.append(v)

    if len(order) != len(in_deg):
        raise ValueError("Cycle detected or graph has unknown nodes")

    return order
