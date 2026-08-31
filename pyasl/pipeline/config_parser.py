import logging
import os
import time
from typing import Any, Dict, List
import yaml
from pydantic import BaseModel, ValidationError
from .pipeline import Pipeline
from .node import Node
from .exceptions.errors import InvalidPipelineError

logger = logging.getLogger("pyasl.pipeline.config_parser")


def _adapt_legacy_format(raw: dict) -> dict:
    """
    Convert old-style YAML configs (type / steps / module or name / params)
    to the new PipelineSchema format (pipeline / nodes).

    Old format example::

        type: pcasl
        steps:
          - module: BrukerLoader
            params: {expno: 18}
          - module: SaveOutputs

    New format example::

        pipeline:
          name: pcasl
        nodes:
          - id: node_0
            function: BrukerLoader
            inputs:
              expno: 18

    If the dict already contains a ``nodes`` key the data is returned unchanged.
    """
    if "nodes" in raw:
        logger.info("  [config]  Format check: 'nodes' key found — already in new format, no adaptation needed.")
        return raw

    if "steps" not in raw:
        logger.warning("  [config]  Format check: neither 'nodes' nor 'steps' key found — passing raw to schema validator.")
        return raw

    logger.info("  [config]  Format check: legacy 'steps' format detected — adapting to 'nodes' schema.")
    steps = raw.get("steps") or []
    logger.info("  [config]    step_count = %d", len(steps))

    pipeline_meta: Dict[str, Any] = {}
    if "type" in raw:
        pipeline_meta["name"] = raw["type"]
        logger.info("  [config]    pipeline name from 'type' key: '%s'", raw["type"])

    nodes: List[Dict[str, Any]] = []
    prev_id = None
    for idx, step in enumerate(steps):
        function_name = step.get("module") or step.get("name") or f"step_{idx}"
        node_id = f"node_{idx}"
        params = step.get("params") or {}
        node: Dict[str, Any] = {
            "id": node_id,
            "function": function_name,
            "inputs": params if isinstance(params, dict) else {},
            "depends_on": [prev_id] if prev_id is not None else [],
        }
        nodes.append(node)
        logger.info("  [config]    adapted step %d -> id='%s'  fn='%s'  params=%s  deps=%s",
                    idx, node_id, function_name, list(params.keys()) if isinstance(params, dict) else params,
                    node["depends_on"] or "(none)")
        prev_id = node_id

    logger.info("  [config]  Adaptation complete: %d node(s) generated.", len(nodes))
    return {
        "pipeline": pipeline_meta,
        "nodes": nodes,
    }


class NodeSchema(BaseModel):
    id: str
    function: str
    depends_on: List[str] = []
    inputs: Dict[str, Any] = {}
    outputs: List[str] = []
    config: Dict[str, Any] = {}

    try:
        from pydantic import field_validator
        @field_validator('id')
        @classmethod
        def no_dots(cls, v: str) -> str:
            if isinstance(v, str) and '.' in v:
                raise ValueError("Node IDs cannot contain '.'")
            return v
    except (ImportError, AttributeError):
        from pydantic import validator  # type: ignore
        @validator('id')  # type: ignore
        def no_dots(cls, v: str) -> str:
            if isinstance(v, str) and '.' in v:
                raise ValueError("Node IDs cannot contain '.'")
            return v


class PipelineSchema(BaseModel):
    pipeline: Dict[str, Any] = {}
    nodes: List[NodeSchema]


def validate_yaml_config(path: str) -> PipelineSchema:
    """
    Validate YAML pipeline configuration file against schema.
    Returns parsed PipelineSchema or raises InvalidPipelineError with line numbers.
    """
    # ── Step: file existence checks ───────────────────────────────────────────
    logger.info("  [config]  Validating YAML config:")
    logger.info("  [config]    path = %s", path)

    if not os.path.exists(path):
        logger.error("  [config]    ERROR: file does not exist: %s", path)
        raise InvalidPipelineError(f"Config path does not exist: '{path}'")
    if not os.path.isfile(path):
        logger.error("  [config]    ERROR: path is not a file: %s", path)
        raise InvalidPipelineError(f"Config path is not a file: '{path}'")

    size = os.path.getsize(path)
    logger.info("  [config]    file exists: YES  size=%d bytes", size)

    # ── Step: parse YAML ──────────────────────────────────────────────────────
    logger.info("  [config]  Parsing YAML content ...")
    with open(path, "r", encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            line_str = ""
            if hasattr(exc, "problem_mark") and exc.problem_mark:
                mark = exc.problem_mark
                line_str = f" at Line {mark.line + 1}, Column {mark.column + 1}"
            logger.error("  [config]  YAML syntax error%s: %s", line_str, exc)
            raise InvalidPipelineError(f"YAML Syntax Error{line_str}: {exc}") from exc

    if not isinstance(raw, dict):
        logger.error("  [config]  ERROR: YAML root must be a dict, got %s", type(raw).__name__)
        raise InvalidPipelineError("YAML content must be a dictionary containing 'nodes'")

    top_keys = list(raw.keys())
    logger.info("  [config]  YAML parsed OK  top-level keys: %s", top_keys)

    # ── Step: adapt format if legacy ──────────────────────────────────────────
    raw = _adapt_legacy_format(raw)

    # ── Step: validate against schema ─────────────────────────────────────────
    logger.info("  [config]  Running schema validation (PipelineSchema) ...")
    try:
        schema_data = PipelineSchema.parse_obj(raw)
    except ValidationError as exc:
        details = []
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err["loc"])
            details.append(f"Field [{loc}]: {err['msg']}")
            logger.error("  [config]    schema error: %s -> %s", loc, err["msg"])
        raise InvalidPipelineError(f"YAML Schema Validation Error: {'; '.join(details)}") from exc

    pipeline_name = schema_data.pipeline.get("name", "unnamed")
    logger.info("  [config]  Schema validation PASSED:")
    logger.info("  [config]    pipeline_name = '%s'", pipeline_name)
    logger.info("  [config]    node_count    = %d", len(schema_data.nodes))
    for n in schema_data.nodes:
        logger.info("  [config]      node id='%s'  fn='%s'  inputs=%s  deps=%s",
                    n.id, n.function,
                    list(n.inputs.keys()) or "(none)",
                    n.depends_on or "(none)")

    return schema_data


def parse_yaml_file(path: str) -> Pipeline:
    logger.info("  [config]  Building Pipeline object from YAML: %s", os.path.basename(path))

    data = validate_yaml_config(path)
    pl = Pipeline(name=data.pipeline.get("name", "pipeline"))

    logger.info("  [config]  Pipeline('%s') created — adding %d node(s) ...",
                pl.name, len(data.nodes))

    for i, n in enumerate(data.nodes, 1):
        node = Node(
            node_id=n.id,
            function_name=n.function,
            depends_on=n.depends_on,
            inputs=n.inputs,
            outputs=n.outputs,
            config=n.config,
        )
        pl.add_node(node)
        logger.info("  [config]    [%d/%d] Added node id='%s'  fn='%s'  "
                    "inputs=%s  depends_on=%s  config_keys=%s",
                    i, len(data.nodes),
                    n.id, n.function,
                    list(n.inputs.keys()) or "(none)",
                    n.depends_on or "(none)",
                    list(n.config.keys()) or "(none)")

    logger.info("  [config]  Pipeline object ready: '%s'  total_nodes=%d",
                pl.name, len(pl.nodes))
    return pl
