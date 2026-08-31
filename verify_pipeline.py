"""
Standalone verification script for the PyASL pipeline framework.
Run from project root: python verify_pipeline.py
"""
import sys
import types

# ---- isolate from heavy pyasl top-level imports ----
sys.path.insert(0, "PyASL")
fake_pyasl = types.ModuleType("pyasl")
fake_pyasl.__path__ = ["PyASL/pyasl"]
fake_pyasl.__package__ = "pyasl"
sys.modules["pyasl"] = fake_pyasl

from pyasl.pipeline.graph import build_graph, topological_sort
from pyasl.pipeline.validator import validate_pipeline
from pyasl.pipeline.exceptions.errors import CycleDetectedError, InvalidPipelineError
from pyasl.pipeline.pipeline import Pipeline
from pyasl.pipeline.node import Node, NodeStatus
from pyasl.pipeline.registry import register, Registry
from pyasl.pipeline.wrappers import run_wrapper
from pyasl.pipeline.logger import node_log, pipeline_log
from pyasl.pipeline.execution_context import ExecutionContext

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []


def check(name, cond, detail=""):
    if cond:
        print(f"  [{PASS}] {name}")
        results.append((name, True))
    else:
        print(f"  [{FAIL}] {name}  -> {detail}")
        results.append((name, False))


# ============================================================
print("\n=== 1. Graph & Topological Sort ===")
nodes = [
    {"id": "a", "depends_on": []},
    {"id": "b", "depends_on": ["a"]},
    {"id": "c", "depends_on": ["b"]},
]
g = build_graph(nodes)
order = topological_sort(g)
check("Linear topo sort [a->b->c]", order == ["a", "b", "c"], order)

# diamond DAG
nodes_d = [
    {"id": "root", "depends_on": []},
    {"id": "left", "depends_on": ["root"]},
    {"id": "right", "depends_on": ["root"]},
    {"id": "merge", "depends_on": ["left", "right"]},
]
g_d = build_graph(nodes_d)
order_d = topological_sort(g_d)
check("Diamond DAG: root before left/right, merge last",
      order_d.index("root") < order_d.index("left")
      and order_d.index("root") < order_d.index("right")
      and order_d[-1] == "merge", order_d)

# ============================================================
print("\n=== 2. Cycle Detection ===")
nodes_cycle = [
    {"id": "a", "depends_on": ["c"]},
    {"id": "b", "depends_on": ["a"]},
    {"id": "c", "depends_on": ["b"]},
]
try:
    validate_pipeline(nodes_cycle)
    check("Cycle detected (a->c->b->a)", False, "No error raised")
except CycleDetectedError:
    check("Cycle detected (a->c->b->a)", True)

# ============================================================
print("\n=== 3. Validator — Duplicate & Self-dependency ===")
try:
    validate_pipeline([{"id": "x", "depends_on": []}, {"id": "x", "depends_on": []}])
    check("Duplicate id rejected", False)
except InvalidPipelineError:
    check("Duplicate id rejected", True)

try:
    validate_pipeline([{"id": "x", "depends_on": ["x"]}])
    check("Self-dependency rejected", False)
except InvalidPipelineError:
    check("Self-dependency rejected", True)

try:
    validate_pipeline([{"id": "a", "depends_on": ["missing"]}])
    check("Unknown dependency rejected", False)
except InvalidPipelineError:
    check("Unknown dependency rejected", True)

# ============================================================
print("\n=== 4. Registry ===")
local_reg = Registry()

@local_reg.register("my_func")
def _dummy(p):
    return {"status": "success", "outputs": {"x": 1}}

check("Named registration found", local_reg.get("my_func") is _dummy)
try:
    local_reg.get("nonexistent")
    check("Missing key raises KeyError", False)
except KeyError:
    check("Missing key raises KeyError", True)

# ============================================================
print("\n=== 5. Node Execution ===")
n = Node(node_id="test_node", function_name="my_func")
n.function = _dummy
out = n.execute({"x": 1})
check("Node executes and returns dict", isinstance(out, dict))
check("Node status COMPLETED on success", n.status == NodeStatus.COMPLETED)
check("execution_time present", "execution_time" in out)

# failing node
def _bad(p):
    raise RuntimeError("boom")

n_bad = Node(node_id="bad_node", function_name="bad")
n_bad.function = _bad
out_bad = n_bad.execute({})
check("Node status FAILED on exception", n_bad.status == NodeStatus.FAILED)
check("Error captured in result", "error" in out_bad)

# ============================================================
print("\n=== 6. Pipeline End-to-End with Data Passing ===")
global_reg = __import__("pyasl.pipeline.registry", fromlist=["registry"]).registry

@global_reg.register("e2e_load")
def _load(payload):
    return {"outputs": {"raw_data": "raw"}}

@global_reg.register("e2e_motion")
def _motion(payload):
    inputs = payload.get("inputs", {})
    raw = inputs.get("raw_data")
    return {"outputs": {"corrected_data": f"{raw}_corrected"}}

@global_reg.register("e2e_quant")
def _quant(payload):
    inputs = payload.get("inputs", {})
    corr = inputs.get("corrected_data")
    return {"outputs": {"cbf_map": f"{corr}_cbf"}}

n1 = Node(node_id="import_data", function_name="e2e_load", outputs=["raw_data"])
n2 = Node(
    node_id="motion_correction",
    function_name="e2e_motion",
    depends_on=["import_data"],
    inputs={"raw_data": "import_data.raw_data"},
    outputs=["corrected_data"],
)
n3 = Node(
    node_id="quantification",
    function_name="e2e_quant",
    depends_on=["motion_correction"],
    inputs={"corrected_data": "motion_correction.corrected_data"},
    outputs=["cbf_map"],
)

pl = Pipeline("asl_test_pipeline")
pl.add_node(n1)
pl.add_node(n2)
pl.add_node(n3)
res = pl.execute()

check("Pipeline status = completed", res["status"] == "completed", res["status"])
cbf = pl.nodes["quantification"].result["outputs"]["cbf_map"]
check("Data flows: cbf_map == 'raw_corrected_cbf'", cbf == "raw_corrected_cbf", cbf)
check("execution_log has 3 entries", len(res["execution_log"]) == 3, len(res["execution_log"]))
check("duration recorded (>= 0)", res["duration"] >= 0)

# ============================================================
print("\n=== 7. Pipeline Failure Propagation ===")
global_reg.register("bad_step")(lambda p: 1/0)

pl_fail = Pipeline("fail_test")
pl_fail.add_node(Node(node_id="step1", function_name="bad_step"))
res_fail = pl_fail.execute()
check("Pipeline status = failed when node fails", res_fail["status"] == "failed")
check("Failed node recorded in log", res_fail["execution_log"][0]["status"] == "FAILED")

# ============================================================
print("\n=== 8. Duplicate Node Rejected ===")
pl2 = Pipeline("dup_test")
pl2.add_node(Node(node_id="n1", function_name="e2e_load"))
try:
    pl2.add_node(Node(node_id="n1", function_name="e2e_load"))
    check("Duplicate node_id raises ValueError", False)
except ValueError:
    check("Duplicate node_id raises ValueError", True)

# ============================================================
print("\n=== 9. run_wrapper helper ===")
def raw_func(inputs, config, metadata):
    return {"status": "success", "outputs": {"result": inputs.get("x", 0) * 2}}

wrapped = run_wrapper(raw_func)
out_w = wrapped({"inputs": {"x": 5}, "config": {}, "metadata": {}})
check("run_wrapper returns dict", isinstance(out_w, dict))
check("run_wrapper result correct (5*2=10)", out_w["outputs"]["result"] == 10)

# ============================================================
print("\n=== 10. Logger ===")
import json
log_str = node_log({"node_id": "x", "status": "COMPLETED"})
parsed = json.loads(log_str)
check("node_log produces valid JSON with timestamp", "timestamp" in parsed)

pl_log = pipeline_log({"pipeline": "test", "status": "completed"})
parsed_pl = json.loads(pl_log)
check("pipeline_log produces valid JSON", "timestamp" in parsed_pl)

# ============================================================
print("\n=== 11. ExecutionContext ===")
ctx = ExecutionContext()
ctx.set("key1", [1, 2, 3])
check("ExecutionContext stores and retrieves values", ctx.get("key1") == [1, 2, 3])
check("ExecutionContext returns default for missing key", ctx.get("nope", "default") == "default")

# ============================================================
print("\n" + "=" * 52)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"  Result: {passed}/{total} checks passed")
if passed == total:
    print("  \033[92mALL CHECKS PASSED - Framework is working correctly\033[0m")
else:
    print("  \033[91mSome checks failed - review above\033[0m")
    sys.exit(1)
