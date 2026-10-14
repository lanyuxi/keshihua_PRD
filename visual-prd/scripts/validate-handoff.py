#!/usr/bin/env python3
"""Validate requirement identity and cross-artifact handoff links with stdlib only."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


LINK_TYPES = {
    "PROTOTYPE_ANCHOR": "--prototype",
    "ANNOTATION": "--annotations",
    "METRIC": "--metrics",
    "QUALITY_ISSUE": "--quality-report",
    "ACCEPTANCE_CASE": "--acceptance-plan",
}
LOCATOR_TYPES = {"SOURCE_LINE", "HEADING", "PAGE", "PDF_REGION", "JSON_PATH", "DOM_SELECTOR", "IMAGE_REGION", "TIMESTAMP", "MISSING"}
ID_RE = re.compile(r"^[^\s]+$")
ANCHOR_RE = re.compile(r"\bdata-anno\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and bool(ID_RE.fullmatch(value))


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def ids(items: object, label: str, errors: list[str]) -> set[str]:
    result: set[str] = set()
    if not isinstance(items, list):
        errors.append(f"{label} 必须是数组")
        return result
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not nonempty(item.get("id")):
            errors.append(f"{label}[{index}].id 必须是非空且无空白的字符串")
            continue
        identity = item["id"]
        if identity in result:
            errors.append(f"{label} 中 ID 重复：{identity}")
        result.add(identity)
    return result


def validate_manifest(manifest: object, baseline: object | None = None) -> tuple[list[str], dict[str, set[str]]]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["交接文件顶层必须是 JSON 对象"], {}
    for key in ("schema_version", "artifact_id", "product", "input_version", "source_artifacts", "requirements", "links", "open_questions"):
        if key not in manifest:
            errors.append(f"缺少顶层字段：{key}")
    if errors:
        return errors, {}
    if manifest["schema_version"] != "1.0":
        errors.append("schema_version 必须为 1.0")
    for key in ("artifact_id", "product", "input_version"):
        if not text(manifest.get(key)):
            errors.append(f"{key} 不能为空")

    artifact_ids = ids(manifest["source_artifacts"], "source_artifacts", errors)
    for index, artifact in enumerate(manifest["source_artifacts"] if isinstance(manifest["source_artifacts"], list) else []):
        if isinstance(artifact, dict):
            for key in ("source", "version"):
                if not text(artifact.get(key)):
                    errors.append(f"source_artifacts[{index}].{key} 不能为空")

    requirement_ids = ids(manifest["requirements"], "requirements", errors)
    for index, requirement in enumerate(manifest["requirements"] if isinstance(manifest["requirements"], list) else []):
        if not isinstance(requirement, dict):
            continue
        prefix = f"requirements[{index}]"
        if not text(requirement.get("title")):
            errors.append(f"{prefix}.title 不能为空")
        status = requirement.get("status")
        if status not in {"ACTIVE", "RETIRED"}:
            errors.append(f"{prefix}.status 必须为 ACTIVE 或 RETIRED")
        source = requirement.get("source")
        if not isinstance(source, dict) or source.get("artifact") not in artifact_ids or source.get("type") not in LOCATOR_TYPES or not isinstance(source.get("value"), (str, int)) or not str(source.get("value")).strip():
            errors.append(f"{prefix}.source 必须定位到 source_artifacts 中的原始材料")
        for key in ("roles", "business_rules"):
            values = requirement.get(key)
            if not isinstance(values, list) or not all(text(value) for value in values):
                errors.append(f"{prefix}.{key} 必须是字符串数组")
            elif key == "roles" and len(values) != len(set(values)):
                errors.append(f"{prefix}.roles 不得重复")
        criteria = requirement.get("acceptance_criteria")
        if not isinstance(criteria, list):
            errors.append(f"{prefix}.acceptance_criteria 必须是数组")
        else:
            criterion_ids: set[str] = set()
            for criterion_index, criterion in enumerate(criteria):
                if not isinstance(criterion, dict) or not nonempty(criterion.get("id")) or not text(criterion.get("text")):
                    errors.append(f"{prefix}.acceptance_criteria[{criterion_index}] 必须包含 id 和 text")
                elif criterion["id"] in criterion_ids:
                    errors.append(f"{prefix}.acceptance_criteria ID 重复：{criterion['id']}")
                else:
                    criterion_ids.add(criterion["id"])

    links = manifest["links"]
    mapped: dict[str, set[str]] = {kind: set() for kind in LINK_TYPES}
    seen_links: set[tuple[str, str, str]] = set()
    if not isinstance(links, list):
        errors.append("links 必须是数组")
    else:
        for index, link in enumerate(links):
            prefix = f"links[{index}]"
            if not isinstance(link, dict):
                errors.append(f"{prefix} 必须是对象")
                continue
            requirement_id = link.get("requirement_id")
            kind = link.get("target_type")
            target_id = link.get("target_id")
            if not isinstance(requirement_id, str) or requirement_id not in requirement_ids:
                errors.append(f"{prefix}.requirement_id 未命中需求：{requirement_id}")
            if not isinstance(kind, str) or kind not in LINK_TYPES:
                errors.append(f"{prefix}.target_type 无效：{kind}")
            if not nonempty(target_id):
                errors.append(f"{prefix}.target_id 必须非空且无空白")
            if kind in LINK_TYPES and nonempty(target_id):
                mapped[kind].add(target_id)
            if nonempty(requirement_id) and kind in LINK_TYPES and nonempty(target_id):
                key = (requirement_id, kind, target_id)
                if key in seen_links:
                    errors.append(f"{prefix} 重复链接：{requirement_id} → {kind}:{target_id}")
                seen_links.add(key)

    question_ids = ids(manifest["open_questions"], "open_questions", errors)
    for index, question in enumerate(manifest["open_questions"] if isinstance(manifest["open_questions"], list) else []):
        if not isinstance(question, dict):
            continue
        if not text(question.get("question")):
            errors.append(f"open_questions[{index}].question 不能为空")
        references = question.get("requirement_ids")
        if not isinstance(references, list) or not references:
            errors.append(f"open_questions[{index}].requirement_ids 至少引用一条需求")
        else:
            for reference in references:
                if not isinstance(reference, str) or reference not in requirement_ids:
                    errors.append(f"open_questions[{index}] 引用不存在的需求：{reference}")

    if baseline is not None:
        if not isinstance(baseline, dict) or not isinstance(baseline.get("requirements"), list):
            errors.append("基线文件缺少 requirements 数组")
        else:
            if baseline.get("product") != manifest.get("product"):
                errors.append("基线与当前文件的 product 不一致")
            baseline_requirements = {item.get("id"): item for item in baseline["requirements"] if isinstance(item, dict) and nonempty(item.get("id"))}
            missing = sorted(set(baseline_requirements) - requirement_ids)
            if missing:
                errors.append("旧版本需求 ID 被直接删除；请保留并标记 RETIRED：" + ", ".join(missing))
            current = {item.get("id"): item for item in manifest["requirements"] if isinstance(item, dict) and nonempty(item.get("id"))}
            for requirement_id, prior in baseline_requirements.items():
                if prior.get("status") == "RETIRED" and requirement_id in current and current[requirement_id].get("status") != "RETIRED":
                    errors.append(f"已废弃需求 ID 不得重新启用：{requirement_id}")
    return errors, mapped


def target_ids(path: Path, kind: str) -> tuple[set[str], dict[str, set[str]], set[str]]:
    if kind == "PROTOTYPE_ANCHOR":
        source = path.read_text(encoding="utf-8")
        return {match.group(2) for match in ANCHOR_RE.finditer(source)}, {}, set()
    value = read_json(path)
    if kind == "ANNOTATION":
        items = value
        key = "id"
    elif kind == "METRIC":
        items = value.get("metrics") if isinstance(value, dict) else value
        key = "id"
    elif kind == "QUALITY_ISSUE":
        items = value.get("issues") if isinstance(value, dict) else None
        key = "id"
    else:
        items = value.get("test_cases") if isinstance(value, dict) else None
        key = "id"
    if not isinstance(items, list):
        raise ValueError(f"{kind} 文件缺少可读取的对象列表")
    objects = [item for item in items if isinstance(item, dict) and nonempty(item.get(key))]
    references: dict[str, set[str]] = {}
    if kind == "ACCEPTANCE_CASE":
        for item in objects:
            refs = item.get("requirement_ids")
            if isinstance(refs, list):
                references[item["id"]] = {str(ref) for ref in refs}
    requirement_ids: set[str] = set()
    if kind == "ACCEPTANCE_CASE" and isinstance(value, dict):
        requirements = value.get("requirements")
        if isinstance(requirements, list):
            requirement_ids = {item["id"] for item in requirements if isinstance(item, dict) and nonempty(item.get("id"))}
    return {item[key] for item in objects}, references, requirement_ids


def check_targets(manifest: dict[str, object], mapped: dict[str, set[str]], supplied: dict[str, Path | None]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    unchecked: list[str] = []
    links = manifest.get("links", [])
    for kind, option in LINK_TYPES.items():
        targets = mapped.get(kind, set())
        path = supplied.get(kind)
        if path is None:
            if targets:
                unchecked.append(f"{kind}（未提供 {option}）")
            continue
        found, embedded_refs, embedded_requirements = target_ids(path, kind)
        missing = sorted(targets - found)
        if missing:
            errors.append(f"{kind} 链接目标未命中：{', '.join(missing)}")
        if kind == "QUALITY_ISSUE":
            quality_value = read_json(path)
            if not isinstance(quality_value, dict) or not isinstance(quality_value.get("traceability"), list):
                raise ValueError("质量报告缺少可读取的 traceability 列表")
            linked_issues = {
                (item.get("requirement_id"), item.get("target_id"))
                for item in links
                if isinstance(item, dict) and item.get("target_type") == kind
            }
            for row in quality_value["traceability"]:
                if not isinstance(row, dict) or not isinstance(row.get("issue_refs"), list):
                    continue
                requirement_id = row.get("requirement_id")
                for issue_id in row["issue_refs"]:
                    if not isinstance(issue_id, str) or not isinstance(requirement_id, str):
                        errors.append("质量报告追踪矩阵中的需求或问题 ID 无效")
                        continue
                    if (requirement_id, issue_id) not in linked_issues:
                        errors.append(f"质量问题 {issue_id} 未写入交接链接：{requirement_id}")
        if kind == "ACCEPTANCE_CASE":
            manifest_ids = {item["id"] for item in manifest.get("requirements", []) if isinstance(item, dict) and nonempty(item.get("id")) and item.get("status") == "ACTIVE"}
            unknown_requirements = sorted(embedded_requirements - manifest_ids)
            if unknown_requirements:
                errors.append("验收方案出现交接文件中不存在或已废弃的需求 ID：" + ", ".join(unknown_requirements))
            acceptance_value = read_json(path)
            upstream_by_id = {item["id"]: item for item in manifest.get("requirements", []) if isinstance(item, dict) and nonempty(item.get("id"))}
            for item in acceptance_value.get("requirements", []) if isinstance(acceptance_value, dict) else []:
                if isinstance(item, dict) and item.get("id") in upstream_by_id and item.get("source") != upstream_by_id[item["id"]].get("source"):
                    errors.append(f"验收需求 {item['id']} 的原始来源定位与交接文件不一致")
            linked_refs: dict[str, set[str]] = {}
            for item in links:
                if isinstance(item, dict) and item.get("target_type") == kind and nonempty(item.get("target_id")):
                    linked_refs.setdefault(item["target_id"], set()).add(str(item.get("requirement_id")))
            for case_id, refs in embedded_refs.items():
                if case_id not in linked_refs:
                    errors.append(f"验收用例 {case_id} 未写入交接链接")
                elif refs != linked_refs[case_id]:
                    errors.append(f"验收用例 {case_id} 的 requirement_ids 与交接链接不一致")
    return errors, unchecked


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate requirement handoff identity and links.")
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--prototype", type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--quality-report", type=Path)
    parser.add_argument("--acceptance-plan", type=Path)
    args = parser.parse_args()
    try:
        manifest = read_json(args.handoff)
        baseline = read_json(args.baseline) if args.baseline else None
        errors, mapped = validate_manifest(manifest, baseline)
        unchecked: list[str] = []
        if not errors:
            target_errors, unchecked = check_targets(manifest, mapped, {
                "PROTOTYPE_ANCHOR": args.prototype,
                "ANNOTATION": args.annotations,
                "METRIC": args.metrics,
                "QUALITY_ISSUE": args.quality_report,
                "ACCEPTANCE_CASE": args.acceptance_plan,
            })
            errors.extend(target_errors)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"FAIL: 无法验证交接文件：{error}", file=sys.stderr)
        raise SystemExit(1)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"PASS: {len(manifest['requirements'])} 条需求 ID、来源和链接结构有效")
    if unchecked:
        print("UNVERIFIED: " + "；".join(unchecked))
    else:
        print("PASS: 所有已声明的下游链接均已命中")


if __name__ == "__main__":
    main()
