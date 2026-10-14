#!/usr/bin/env python3
"""Compile annotation JSON from facts and anchors in the product model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_core import dump_json, iter_annotated_nodes, load_model, validate_model


def compile_annotations(model: dict) -> list[dict]:
    index = validate_model(model)
    result: list[dict] = []
    for node, annotation, page_id, _ in iter_annotated_nodes(model):
        if not annotation:
            continue
        scope = annotation.get("scope") or {"type": "page", "id": page_id}
        requirement_ids = node.get("requirement_ids", [])
        first_requirement = index["requirements"].get(requirement_ids[0]) if requirement_ids else None
        title = annotation.get("title") or node.get("label") or node.get("title") or node.get("name") or annotation["id"]
        body = annotation.get("summary") or node.get("description") or (first_requirement or {}).get("description") or "待确认"
        rules = [index["rules"][rule_id]["text"] + ("（待确认）" if index["rules"][rule_id]["status"] == "PENDING" else "") for rule_id in annotation.get("rule_refs", [])]
        criteria = [index["criteria"][criterion_id]["text"] + ("（待确认）" if index["criteria"][criterion_id]["status"] == "PENDING" else "") for criterion_id in annotation.get("acceptance_refs", [])]
        if criteria:
            body = f"{body}\n验收：" + "；".join(criteria)
        result.append({
            "id": annotation["id"],
            "order": annotation["order"],
            "pageId": str(page_id),
            "title": str(title),
            "body": str(body),
            "businessRules": rules,
            "scope": {"type": scope["type"], "id": scope["id"]},
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="从产品模型生成标注 JSON")
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", "-o", type=Path, required=True)
    args = parser.parse_args()
    try:
        annotations = compile_annotations(load_model(args.model))
        dump_json(annotations, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"PASS: 已生成 {len(annotations)} 条标注到 {args.output}")


if __name__ == "__main__":
    main()
