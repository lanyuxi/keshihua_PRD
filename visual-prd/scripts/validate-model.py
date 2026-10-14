#!/usr/bin/env python3
"""Validate one canonical Visual PRD product model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_core import iter_annotated_nodes, load_model, validate_model


def main() -> None:
    parser = argparse.ArgumentParser(description="校验 Visual PRD 产品模型")
    parser.add_argument("model", type=Path)
    args = parser.parse_args()
    try:
        model = load_model(args.model)
        indexes = validate_model(model)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    annotation_count = sum(1 for _, annotation, _, _ in iter_annotated_nodes(model) if annotation)
    print(f"PASS: {args.model}，{len(indexes['requirements'])} 项需求，{len(indexes['pages'])} 个页面，{annotation_count} 个直接标注")


if __name__ == "__main__":
    main()
