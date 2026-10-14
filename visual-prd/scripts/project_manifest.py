#!/usr/bin/env python3
"""Load and validate Visual PRD project manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VALID_MODES = {"assemble", "enhance", "generate"}
REQUIRED_INPUTS = {
    "assemble": {"prd", "prototype", "annotations"},
    "enhance": {"prd", "prototype", "annotations"},
    "generate": {"product_model"},
}
OPTIONAL_INPUTS = {
    "assemble": {"handoff", "flows"},
    "enhance": {"handoff", "flows"},
    "generate": {"ui_profile", "flows"},
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "项目清单根节点必须是 object")
    require(value.get("schema_version") == "1.0", "项目清单 schema_version 必须为 1.0")
    mode = value.get("mode")
    require(mode in VALID_MODES, "项目清单 mode 必须为 assemble、enhance 或 generate")
    require(isinstance(value.get("output_dir"), str) and bool(value["output_dir"].strip()), "output_dir 不能为空")
    inputs = value.get("inputs")
    require(isinstance(inputs, dict), "inputs 必须是 object")
    missing = REQUIRED_INPUTS[mode] - set(inputs)
    require(not missing, f"{mode} 模式缺少输入: {', '.join(sorted(missing))}")
    allowed = REQUIRED_INPUTS[mode] | OPTIONAL_INPUTS[mode]
    unknown = set(inputs) - allowed
    require(not unknown, f"{mode} 模式存在无效输入: {', '.join(sorted(unknown))}")
    for key, source in inputs.items():
        require(isinstance(source, str) and bool(source.strip()), f"inputs.{key} 必须是非空路径")
    prototype = value.get("prototype", {})
    require(isinstance(prototype, dict), "prototype 必须是 object")
    require(not (set(prototype) - {"page_id"}), "prototype 存在未知字段")
    if "page_id" in prototype:
        require(isinstance(prototype["page_id"], str) and bool(prototype["page_id"].strip()), "prototype.page_id 不能为空")
    require(not (set(value) - {"schema_version", "mode", "output_dir", "inputs", "prototype"}), "项目清单存在未知字段")
    return value


def resolve_path(manifest_path: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    return candidate.resolve()


def resolved_inputs(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    result = {key: resolve_path(manifest_path, value) for key, value in manifest["inputs"].items()}
    missing = [f"{key}: {path}" for key, path in result.items() if not path.is_file()]
    require(not missing, "输入文件不存在: " + "; ".join(missing))
    return result
