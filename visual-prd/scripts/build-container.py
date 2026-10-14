#!/usr/bin/env python3
"""Build a visual PRD page from the bundled container assets."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

from ui_profile import load_ui_profile


SKILL_ROOT = Path(__file__).resolve().parent.parent
ANNOTATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
VALID_SCOPES = {"page", "tab", "drawer", "modal"}


def encode_payload(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def strip_demo_fallbacks(template: str) -> str:
    """Keep the reusable asset illustrative, but omit demo payloads from built deliverables."""
    pattern = re.compile(
        r"\s*const DEFAULT_PROTOTYPE = String\.raw`.*?\n\s*const DOC_META =",
        re.DOTALL,
    )
    replacement = (
        '\n      const DEFAULT_PROTOTYPE = "";\n'
        '      const DEFAULT_DOCS = { architecture: "", roles: "", rules: "" };\n'
        '      const DEFAULT_ANNOTATIONS = [];\n\n'
        '      const DOC_META ='
    )
    result, count = pattern.subn(replacement, template, count=1)
    if count != 1:
        raise ValueError("Container template demo fallback block could not be stripped")
    return result


def load_annotations(path: Path | None) -> list[dict]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Annotations file must contain a JSON array")
    validate_annotations(value)
    return value


def validate_annotations(annotations: list[dict]) -> None:
    seen_ids: set[str] = set()
    for annotation in annotations:
        if not isinstance(annotation, dict):
            raise ValueError("Every annotation must be a JSON object")
        required = {"id", "order", "pageId", "title", "body", "businessRules", "scope"}
        missing = sorted(required - annotation.keys())
        if missing:
            raise ValueError(f"Annotation is missing required fields: {', '.join(missing)}")
        annotation_id = str(annotation.get("id", "")).strip()
        if not annotation_id:
            raise ValueError("Every annotation requires a non-empty id")
        if not ANNOTATION_ID.fullmatch(annotation_id):
            raise ValueError(
                f'Annotation id "{annotation_id}" must use letters, digits, hyphens or underscores'
            )
        if annotation_id in seen_ids:
            raise ValueError(f'Duplicate annotation id: "{annotation_id}"')
        seen_ids.add(annotation_id)

        order = annotation.get("order")
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise ValueError(f'Annotation "{annotation_id}" requires a positive integer order')

        page_id = annotation.get("pageId")
        if not isinstance(page_id, str) or not page_id.strip():
            raise ValueError(f'Annotation "{annotation_id}" requires a non-empty pageId')
        if not isinstance(annotation.get("title"), str) or not annotation["title"].strip():
            raise ValueError(f'Annotation "{annotation_id}" requires a non-empty title')
        if not isinstance(annotation.get("body"), str):
            raise ValueError(f'Annotation "{annotation_id}" body must be a string')
        rules = annotation.get("businessRules")
        if not isinstance(rules, (str, list)) or (
            isinstance(rules, list) and not all(isinstance(rule, str) for rule in rules)
        ):
            raise ValueError(f'Annotation "{annotation_id}" businessRules must be a string or string array')
        scope = annotation.get("scope")
        if not isinstance(scope, dict):
            raise ValueError(f'Annotation "{annotation_id}" scope must be an object')
        kind = scope.get("type")
        if kind not in VALID_SCOPES:
            raise ValueError(f'Annotation "{annotation_id}" has unsupported scope type "{kind}"')
        if page_id == "*" and kind != "page":
            raise ValueError(f'Cross-page annotation "{annotation_id}" must use page scope')
        if not isinstance(scope.get("id"), str) or not scope["id"].strip():
            raise ValueError(f'Annotation "{annotation_id}" requires a non-empty scope.id')

    def scope_type(annotation: dict) -> str:
        return str((annotation.get("scope") or {}).get("type", "page"))

    def scope_id(annotation: dict) -> str:
        return str((annotation.get("scope") or {}).get("id", ""))

    def validate_view(label: str, members: list[dict]) -> None:
        orders = sorted(int(member["order"]) for member in members)
        expected = list(range(1, len(members) + 1))
        if orders != expected:
            detail = ", ".join(f'{member["id"]}:{member["order"]}' for member in members)
            raise ValueError(
                f'Visible annotation orders for {label} must be continuous from 1 without duplicates; got {detail}'
            )

    page_ids = sorted({str(item.get("pageId", "*")) for item in annotations if str(item.get("pageId", "*")) != "*"})
    cross_page_base = [
        item for item in annotations
        if str(item.get("pageId", "*")) == "*" and scope_type(item) == "page"
    ]
    if cross_page_base:
        validate_view("cross-page base group", cross_page_base)

    for page_id in page_ids:
        page_members = [item for item in annotations if str(item.get("pageId", "*")) == page_id]
        base = cross_page_base + [item for item in page_members if scope_type(item) == "page"]
        validate_view(f'page "{page_id}" base view', base)

        tab_groups: dict[str, list[dict]] = {}
        overlay_groups: dict[tuple[str, str], list[dict]] = {}
        for item in page_members:
            kind = scope_type(item)
            if kind == "tab":
                tab_groups.setdefault(scope_id(item), []).append(item)
            elif kind in {"drawer", "modal"}:
                overlay_groups.setdefault((kind, scope_id(item)), []).append(item)

        for tab_id, members in tab_groups.items():
            validate_view(f'page "{page_id}" tab "{tab_id}"', base + members)
        for (kind, overlay_id), members in overlay_groups.items():
            validate_view(f'page "{page_id}" {kind} "{overlay_id}"', members)


def validate_prototype_source(source: str, annotations: list[dict]) -> None:
    anchor_ids = re.findall(r'\bdata-anno\s*=\s*["\']([^"\']+)["\']', source, re.IGNORECASE)
    seen: set[str] = set()
    duplicates: set[str] = set()
    for anchor_id in anchor_ids:
        if anchor_id in seen:
            duplicates.add(anchor_id)
        seen.add(anchor_id)
    if duplicates:
        raise ValueError(f"Duplicate data-anno anchors: {', '.join(sorted(duplicates))}")

    annotation_ids = {str(item["id"]) for item in annotations}
    missing_data = sorted(seen - annotation_ids)
    missing_anchors = sorted(annotation_ids - seen)
    if missing_data:
        raise ValueError(f"Prototype anchors missing annotation data: {', '.join(missing_data)}")
    if missing_anchors:
        raise ValueError(f"Annotation data missing prototype anchors: {', '.join(missing_anchors)}")

    external_resource = re.search(
        r'(?:\bsrc\s*=\s*["\']https?://|\brel\s*=\s*["\']stylesheet["\'][^>]*\bhref\s*=\s*["\']https?://|@import\s+(?:url\()?\s*["\']?https?://|url\(\s*["\']?https?://)',
        source,
        re.IGNORECASE,
    )
    if external_resource:
        raise ValueError("Prototype source contains an external runtime resource")


def bundle_prototype(
    source: str,
    runtime: str,
    annotations: list[dict],
    prototype_runtime: str | None = None,
    initialize_annotations: bool = True,
) -> str:
    if "/*__ANNOTATION_RUNTIME__*/" not in source:
        raise ValueError("Prototype source is missing /*__ANNOTATION_RUNTIME__*/")
    if "__ANNOTATION_DATA__" not in source:
        raise ValueError("Prototype source is missing __ANNOTATION_DATA__")
    safe_runtime = runtime.replace("</script", "<\\/script")
    annotation_json = json.dumps(annotations, ensure_ascii=False, separators=(",", ":"))
    annotation_json = annotation_json.replace("</", "<\\/")
    result = source.replace("/*__ANNOTATION_RUNTIME__*/", safe_runtime).replace(
        "__ANNOTATION_DATA__", annotation_json
    )
    if prototype_runtime is not None:
        safe_prototype_runtime = prototype_runtime.replace("</script", "<\\/script")
        script_pattern = re.compile(
            r'<script\s+src=["\'][^"\']*prototype-runtime\.js["\']\s*></script>',
            re.IGNORECASE,
        )
        result, replacements = script_pattern.subn(
            lambda _: f"<script>{safe_prototype_runtime}</script>", result, count=1
        )
        if replacements == 0:
            raise ValueError("Prototype source is missing a prototype-runtime.js script tag")
    if not initialize_annotations:
        result, replacements = re.subn(
            r"window\.AnnotationRuntime\.init\(\{.*?\}\);",
            "window.__VISUAL_PRD_ANNOTATIONS_PENDING__ = true;",
            result,
            count=1,
            flags=re.DOTALL,
        )
        if replacements == 0:
            raise ValueError("Prototype source is missing its annotation runtime initialization")
    return result


def container_annotations(annotations: list[dict]) -> list[dict]:
    result = []
    for annotation in annotations:
        annotation_id = str(annotation["id"])
        escaped_id = annotation_id.replace("\\", "\\\\").replace('"', '\\"')
        scope = annotation.get("scope") or {}
        rules = annotation.get("businessRules") or []
        if isinstance(rules, str):
            rules = [rules]
        result.append(
            {
                "id": annotation_id,
                "order": annotation["order"],
                "pageId": str(annotation.get("pageId", "*")),
                "title": str(annotation.get("title", "未命名标注")),
                "body": str(annotation.get("body", "")),
                "businessRules": rules,
                "selector": f'[data-anno="{escaped_id}"]',
                "scope": str(scope.get("type", "page")),
                "scopeId": str(scope.get("id", "")),
            }
        )
    return result


def developer_source(source: str) -> str:
    """Strip the two review-only scripts before bundling the business runtime."""
    source = re.sub(
        r'<script\b[^>]*>.*?</script>',
        lambda match: "" if (
            "/*__ANNOTATION_RUNTIME__*/" in match.group(0)
            or "__ANNOTATION_DATA__" in match.group(0)
        ) else match.group(0),
        source, flags=re.IGNORECASE | re.DOTALL,
    )
    source = re.sub(r'\s+data-anno(?:-[\w-]+)?\s*=\s*["\'][^"\']*["\']', "", source)
    runtime = (SKILL_ROOT / "scripts/prototype-runtime.js").read_text(encoding="utf-8")
    return re.sub(
        r'<script\s+src=["\'][^"\']*prototype-runtime\.js["\']\s*></script>',
        lambda _: "<script>" + runtime.replace("</script", "<\\/script") + "</script>",
        source, count=1, flags=re.IGNORECASE,
    )


def build(
    prototype_path: Path,
    prd_path: Path,
    output_path: Path,
    annotations_path: Path | None = None,
    runtime_path: Path | None = None,
    prototype_output_path: Path | None = None,
    handoff_path: Path | None = None,
    ui_profile_path: Path | None = None,
    flows_path: Path | None = None,
) -> None:
    template = strip_demo_fallbacks(
        (SKILL_ROOT / "assets/container-template.html").read_text(encoding="utf-8")
    )
    mermaid = (SKILL_ROOT / "assets/mermaid.min.js").read_text(encoding="utf-8")
    template = template.replace("/*__MERMAID_RUNTIME__*/", mermaid.replace("</script", "<\\/script"), 1)
    prototype_source = prototype_path.read_text(encoding="utf-8")
    prd_markdown = prd_path.read_text(encoding="utf-8")
    flows_markdown = flows_path.read_text(encoding="utf-8") if flows_path else ""
    annotations = load_annotations(annotations_path)
    ui_profile = load_ui_profile(ui_profile_path) if ui_profile_path else None
    validate_prototype_source(prototype_source, annotations)
    if handoff_path is not None:
        command = [sys.executable, str(SKILL_ROOT / "scripts/validate-handoff.py"), str(handoff_path), "--prototype", str(prototype_path)]
        if annotations_path is not None:
            command.extend(["--annotations", str(annotations_path)])
        linked = subprocess.run(command, capture_output=True, text=True, check=False)
        if linked.returncode != 0:
            raise ValueError(linked.stderr.strip() or "Requirement handoff validation failed")
    runtime_file = runtime_path or (SKILL_ROOT / "scripts/annotation-runtime.js")
    prototype_runtime_file = SKILL_ROOT / "scripts/prototype-runtime.js"
    prototype_runtime = (
        prototype_runtime_file.read_text(encoding="utf-8")
        if re.search(r'<script\s+src=["\'][^"\']*prototype-runtime\.js["\']\s*></script>', prototype_source, re.IGNORECASE)
        else None
    )
    standalone_prototype_html = bundle_prototype(
        prototype_source,
        runtime_file.read_text(encoding="utf-8"),
        annotations,
        prototype_runtime,
    )

    # The container owns the annotation payload. Its embedded prototype receives
    # the same objects at runtime, avoiding a second copy in the final HTML.
    embedded_prototype_html = bundle_prototype(
        prototype_source,
        runtime_file.read_text(encoding="utf-8"),
        [],
        prototype_runtime,
        initialize_annotations=False,
    )

    if prototype_output_path:
        prototype_output_path.parent.mkdir(parents=True, exist_ok=True)
        prototype_output_path.write_text(standalone_prototype_html, encoding="utf-8")

    page = (
        template.replace(
            "/*__UI_CONFIGURATOR_RUNTIME__*/",
            (SKILL_ROOT / "scripts/ui-configurator-runtime.js").read_text(encoding="utf-8").replace("</script", "<\\/script"),
            1,
        ).replace(
            "__VISUAL_PRD_PROTOTYPE_BASE64__", encode_payload(embedded_prototype_html), 1
        )
        .replace(
            "__VISUAL_PRD_PRD_MARKDOWN_BASE64__", encode_payload(prd_markdown), 1
        )
        .replace(
            "__VISUAL_PRD_ANNOTATIONS_BASE64__",
            encode_payload(json.dumps(container_annotations(annotations), ensure_ascii=False)),
            1,
        ).replace(
            "__VISUAL_PRD_UI_PROFILE_BASE64__",
            encode_payload(json.dumps(ui_profile, ensure_ascii=False)) if ui_profile else "",
            1,
        )
    )
    page = page.replace("__VISUAL_PRD_DEVELOPER_BASE64__", encode_payload(developer_source(prototype_source)), 1)
    page = page.replace("__VISUAL_PRD_FLOWS_BASE64__", encode_payload(flows_markdown), 1)
    unresolved = [
        marker for marker in (
            'const PROTOTYPE_PAYLOAD = "__VISUAL_PRD_PROTOTYPE_BASE64__"',
            'const PRD_PAYLOAD = "__VISUAL_PRD_PRD_MARKDOWN_BASE64__"',
            'const ANNOTATIONS_PAYLOAD = "__VISUAL_PRD_ANNOTATIONS_BASE64__"',
            'const UI_PROFILE_PAYLOAD = "__VISUAL_PRD_UI_PROFILE_BASE64__"',
            "/*__UI_CONFIGURATOR_RUNTIME__*/",
            "/*__MERMAID_RUNTIME__*/",
            'const DEVELOPER_PAYLOAD = "__VISUAL_PRD_DEVELOPER_BASE64__"',
            'const FLOWS_PAYLOAD = "__VISUAL_PRD_FLOWS_BASE64__"',
        ) if marker in page
    ]
    if unresolved:
        raise ValueError("Container template payload markers were not fully replaced")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a visual PRD HTML container.")
    parser.add_argument("--prototype", type=Path, required=True, help="Prototype HTML source")
    parser.add_argument("--prd", type=Path, required=True, help="PRD Markdown file")
    parser.add_argument("--annotations", type=Path, required=True, help="Annotation JSON file")
    parser.add_argument("--flows", type=Path, help="Flow diagrams Markdown with editable Mermaid code blocks")
    parser.add_argument("--runtime", type=Path, help="Annotation runtime JavaScript")
    parser.add_argument("--handoff", type=Path, help="Optional requirement handoff JSON to validate against prototype and annotations")
    parser.add_argument("--ui-profile", type=Path, help="Optional UI profile exposed through the offline configurator")
    parser.add_argument("--prototype-output", type=Path, help="Write the bundled standalone prototype")
    parser.add_argument("--output", type=Path, required=True, help="Output HTML file")
    args = parser.parse_args()
    try:
        build(
            args.prototype,
            args.prd,
            args.output,
            annotations_path=args.annotations,
            runtime_path=args.runtime,
            prototype_output_path=args.prototype_output,
            handoff_path=args.handoff,
            ui_profile_path=args.ui_profile,
            flows_path=args.flows,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
