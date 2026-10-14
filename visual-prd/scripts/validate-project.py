#!/usr/bin/env python3
"""Validate a Visual PRD project manifest and its input paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_manifest import load_manifest, resolved_inputs, resolve_path


def main() -> None:
    parser = argparse.ArgumentParser(description="校验可视化 PRD 项目清单")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        path = args.manifest.resolve()
        manifest = load_manifest(path)
        inputs = resolved_inputs(path, manifest)
        output = resolve_path(path, manifest["output_dir"])
        if output in inputs.values():
            raise ValueError("输出目录不能与输入文件相同")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"PASS: {manifest['mode']} 模式项目清单有效，输入 {len(inputs)} 项")


if __name__ == "__main__":
    main()
