#!/usr/bin/env python3
"""Validate that the Visual PRD skill package is portable and self-contained."""

from __future__ import annotations

import re
import struct
import subprocess
import sys
import tempfile
import json
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_FILES = (
    "SKILL.md",
    "references/prd-template.md",
    "references/annotation-guide.md",
    "references/markdown-render-guide.md",
    "references/security-and-portability.md",
    "references/requirement-handoff.md",
    "references/requirement-handoff.schema.json",
    "references/metrics-and-tracking.md",
    "references/metrics.schema.json",
    "references/interaction-checklist.md",
    "references/troubleshooting.md",
    "references/product-model.schema.json",
    "references/token-efficient-workflow.md",
    "references/operating-modes.md",
    "references/bootstrap-existing.md",
    "references/ui-profile.md",
    "references/ui-profile.schema.json",
    "references/project-manifest.schema.json",
    "assets/container-template.html",
    "assets/container-styles.css",
    "assets/prototype-template.html",
    "assets/metric-plan-template.json",
    "assets/product-model-template.json",
    "assets/ui-profile-template.json",
    "assets/project-manifest-template.json",
    "assets/skill-icon.png",
    "assets/brand-logo.png",
    "assets/mermaid.min.js",
    "assets/mermaid-LICENSE.txt",
    "references/editing-and-export.md",
    "scripts/build-container.py",
    "scripts/model_core.py",
    "scripts/validate-model.py",
    "scripts/render-prd.py",
    "scripts/build-annotations.py",
    "scripts/build-prototype.py",
    "scripts/build-project.py",
    "scripts/build-review.py",
    "scripts/check-flow-build.py",
    "scripts/check-draft-compatibility.js",
    "scripts/check-save-behavior.js",
    "scripts/prototype-text-runtime.js",
    "scripts/check-prototype-text.js",
    "scripts/validate-review-artifact.py",
    "scripts/prepare-prototype.py",
    "scripts/project_manifest.py",
    "scripts/validate-project.py",
    "scripts/ui_profile.py",
    "scripts/validate-ui-profile.py",
    "scripts/build-ui-preview.py",
    "scripts/validate-handoff.py",
    "scripts/validate-metrics.py",
    "scripts/check-interactions.js",
    "scripts/check-generated-behavior.js",
    "scripts/check-ui-configurator.js",
    "scripts/prototype-runtime.js",
    "scripts/annotation-runtime.js",
    "scripts/ui-configurator-runtime.js",
    "scripts/package-skill.py",
)
IGNORED_SYSTEM_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_frontmatter() -> None:
    source = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", source, re.DOTALL)
    require(match is not None, "SKILL.md is missing YAML frontmatter")
    fields = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        require(bool(separator), f"Invalid frontmatter line: {line}")
        fields[key.strip()] = value.strip()
    require({"name", "description"}.issubset(fields), "Frontmatter requires name and description")
    require(fields["name"] == SKILL_ROOT.name, "Skill name must match its directory")
    require(bool(re.fullmatch(r"[a-z0-9-]+", fields["name"])), "Skill name must use lowercase hyphen-case")
    require(bool(fields["description"]), "Skill description cannot be empty")
    require("metadata" in fields, "Frontmatter requires metadata")
    version = fields.get("version", "").strip("\"'")
    require(bool(re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version)), "metadata.version must use semantic versioning")
    author = fields.get("author", "").strip("\"'")
    expected_author = "公众号“" + "A" + "I 翻车现场”的智障研究员"
    require(author == expected_author, "metadata.author does not match the declared original author")
    require(fields.get("display_name_zh", "").strip('"\'') == "可视化产品需求设计", "Chinese display name is missing")
    require(fields.get("icon", "").strip('"\'') == "assets/skill-icon.png", "metadata.icon is invalid")
    require(version == "4.1.11", "visual-prd version is not 4.1.11")
    for target in re.findall(r"\]\(([^)]+)\)", source):
        if "://" not in target and not target.startswith("#"):
            require((SKILL_ROOT / target).exists(), f"Broken local reference: {target}")


def validate_icon() -> None:
    data = (SKILL_ROOT / "assets/skill-icon.png").read_bytes()
    require(data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR", "skill icon is not PNG")
    require(struct.unpack(">II", data[16:24]) == (1024, 1024), "skill icon must be 1024x1024")


def validate_templates() -> None:
    prototype = (SKILL_ROOT / "assets/prototype-template.html").read_text(encoding="utf-8")
    container = (SKILL_ROOT / "assets/container-template.html").read_text(encoding="utf-8")
    for marker in ("/*__ANNOTATION_RUNTIME__*/", "__ANNOTATION_DATA__", "prototype-runtime.js"):
        require(marker in prototype, f"Prototype template is missing {marker}")
    for marker in (
        "__VISUAL_PRD_PROTOTYPE_BASE64__",
        "__VISUAL_PRD_PRD_MARKDOWN_BASE64__",
        "__VISUAL_PRD_ANNOTATIONS_BASE64__",
        "__VISUAL_PRD_UI_PROFILE_BASE64__",
        "/*__UI_CONFIGURATOR_RUNTIME__*/",
        "/*__MERMAID_RUNTIME__*/",
        "__VISUAL_PRD_FLOWS_BASE64__",
        "__VISUAL_PRD_DEVELOPER_BASE64__",
        'data-visual-prd-container="standard"',
        "data-review-mode-toggle",
        "切换为浮动标注",
        "切换为三栏评审",
    ):
        require(marker in container, f"Container template is missing {marker}")
    for path in (SKILL_ROOT / "assets").glob("*"):
        if path.suffix.lower() not in {".html", ".css"}:
            continue
        source = path.read_text(encoding="utf-8")
        require(not re.search(r"(?:src|href)=[\"']https?://", source, re.IGNORECASE), f"External resource found in {path.name}")
    require(">...</" not in prototype, "Prototype template contains unfinished HTML placeholders")
    require("该板块的所有可变数据" not in prototype, "Prototype template contains unfinished state placeholders")


def validate_syntax() -> None:
    for name in (
        "build-container.py", "model_core.py", "validate-model.py", "render-prd.py",
        "build-annotations.py", "build-prototype.py", "build-project.py",
        "build-review.py", "validate-review-artifact.py", "prepare-prototype.py", "project_manifest.py", "validate-project.py",
        "ui_profile.py", "validate-ui-profile.py", "build-ui-preview.py",
        "package-skill.py", "validate-package.py", "validate-handoff.py", "validate-metrics.py",
    ):
        source = (SKILL_ROOT / "scripts" / name).read_text(encoding="utf-8")
        compile(source, f"scripts/{name}", "exec")
    for name in ("check-interactions.js", "check-generated-behavior.js", "check-ui-configurator.js", "prototype-runtime.js", "annotation-runtime.js", "ui-configurator-runtime.js"):
        result = subprocess.run(
            ["node", "--check", str(SKILL_ROOT / "scripts" / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        require(result.returncode == 0, result.stderr.strip() or f"JavaScript syntax check failed: {name}")
    configurator = subprocess.run(
        ["node", str(SKILL_ROOT / "scripts/check-ui-configurator.js")],
        capture_output=True, text=True, check=False,
    )
    require(configurator.returncode == 0, configurator.stdout + configurator.stderr)
    configurator_source = (SKILL_ROOT / "scripts" / "ui-configurator-runtime.js").read_text(encoding="utf-8")
    require('closest("input[data-ui-path]")' in configurator_source and 'closest("select[data-ui-path]")' in configurator_source, "UI fields can be applied twice by overlapping listeners")
    require("app.inert = true" in configurator_source and 'event.key !== "Tab"' in configurator_source, "UI drawer lacks background inertness or focus trapping")
    require(":ui-profile:${original.id}" in configurator_source, "UI drafts are not isolated by profile id")
    prototype_runtime = (SKILL_ROOT / "scripts" / "prototype-runtime.js").read_text(encoding="utf-8")
    require(
        'path === "route"' in prototype_runtime and "params: isPlainObject(nextValue.params)" in prototype_runtime,
        "Prototype runtime does not replace route params atomically",
    )
    require(
        "if (!isEmbeddedDocument())" in prototype_runtime and "configuredRoute = config.initialState?.route" in prototype_runtime,
        "Embedded prototype startup can overwrite the parent route",
    )


def validate_smoke_build() -> None:
    annotations = [
        {
            "id": "template-list", "order": 1, "pageId": "list",
            "title": "列表区域", "body": "展示条目列表。", "businessRules": [],
            "scope": {"type": "page", "id": "list"},
        },
        {
            "id": "template-create", "order": 2, "pageId": "list",
            "title": "创建入口", "body": "打开创建弹层。", "businessRules": [],
            "scope": {"type": "page", "id": "list"},
        },
        {
            "id": "template-create-form", "order": 1, "pageId": "list",
            "title": "创建表单", "body": "提交创建数据。", "businessRules": [],
            "scope": {"type": "modal", "id": "template-create"},
        },
    ]
    with tempfile.TemporaryDirectory(prefix="visual-prd-validate-") as temporary:
        root = Path(temporary)
        prd = root / "prd.md"
        data = root / "annotations.json"
        output = root / "visual-prd.html"
        prototype_output = root / "prototype.html"
        prd.write_text("# 测试 PRD\n\n| 字段 | 说明 |\n| --- | --- |\n| 名称 | 测试 |\n", encoding="utf-8")
        data.write_text(json.dumps(annotations, ensure_ascii=False), encoding="utf-8")
        interaction = subprocess.run(
            ["node", str(SKILL_ROOT / "scripts" / "check-interactions.js"), str(SKILL_ROOT / "assets" / "prototype-template.html")],
            capture_output=True, text=True, check=False,
        )
        require(interaction.returncode == 0, interaction.stdout + interaction.stderr)
        build = subprocess.run(
            [
                sys.executable, str(SKILL_ROOT / "scripts" / "build-container.py"),
                "--prototype", str(SKILL_ROOT / "assets" / "prototype-template.html"),
                "--prd", str(prd), "--annotations", str(data),
                "--prototype-output", str(prototype_output), "--output", str(output),
            ],
            capture_output=True, text=True, check=False,
        )
        require(build.returncode == 0, build.stdout + build.stderr)
        require(output.is_file() and output.stat().st_size > 0, "Smoke build did not create the final HTML")
        require(prototype_output.is_file(), "Smoke build did not create the bundled prototype")
        artifact_check = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/validate-review-artifact.py"), str(output)],
            capture_output=True, text=True, check=False,
        )
        require(artifact_check.returncode == 0, artifact_check.stdout + artifact_check.stderr)


def validate_model_pipeline() -> None:
    model_path = SKILL_ROOT / "assets" / "product-model-template.json"
    model_template = json.loads(model_path.read_text(encoding="utf-8"))
    schema = json.loads((SKILL_ROOT / "references" / "product-model.schema.json").read_text(encoding="utf-8"))
    require(schema.get("title") == "Visual PRD Product Model", "Product model schema is invalid")
    with tempfile.TemporaryDirectory(prefix="visual-prd-model-") as temporary:
        root = Path(temporary)
        output = root / "dist"
        result = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts" / "build-project.py"), str(model_path), "--output-dir", str(output)],
            capture_output=True,
            text=True,
            check=False,
        )
        require(result.returncode == 0, result.stdout + result.stderr)
        expected = ("prd.md", "annotations.json", "prototype-source.html", "prototype.html", "visual-prd.html", "build-report.json")
        require(all((output / name).is_file() for name in expected), "Model pipeline did not produce every artifact")
        prd = (output / "prd.md").read_text(encoding="utf-8")
        annotations = json.loads((output / "annotations.json").read_text(encoding="utf-8"))
        prototype = (output / "prototype-source.html").read_text(encoding="utf-8")
        final = (output / "visual-prd.html").read_text(encoding="utf-8")
        require("任务名称不能为空" in prd, "PRD did not resolve canonical rule text")
        require(any(any("任务名称不能为空" in rule for rule in item["businessRules"]) for item in annotations), "Annotations did not resolve rule refs")
        require('data-anno="create-entry"' in prototype, "Prototype did not compile annotation anchor")
        require('data-action="open-modal:create"' in prototype, "Prototype did not compile action")
        require('data-title="完成方案评审"' in prototype, "Sortable title data was not compiled")
        require('data-params=\'{&quot;taskId&quot;:&quot;task-1&quot;}\'' in prototype, "Row navigation did not compile record params")
        require('data-submit-operation="append" data-submit-target="tasks"' in prototype, "Create form lacks an explicit list mutation contract")
        require('data-anno-scope="modal"' in prototype, "Dialog annotation scope was not normalized to modal")
        require("const listRenderers" in prototype and "handleGeneratedSubmit" in prototype, "Generated list mutation runtime is missing")
        require("patch.lists" in prototype and "generatedRecord(spec.record, values)" in prototype, "Submit handler does not append a generated record")
        require("data-route-context" in prototype, "Detail route context feedback is missing")
        checker = SKILL_ROOT / "scripts/check-interactions.js"
        broken_sort = root / "broken-sort.html"
        broken_sort.write_text(re.sub(r"\sdata-title=([\"'])[^\"']*\1", "", prototype), encoding="utf-8")
        checked = subprocess.run(["node", str(checker), str(broken_sort)], capture_output=True, text=True, check=False)
        require(checked.returncode != 0 and "排序字段" in checked.stdout, "Interaction checker missed a sort field without data")

        broken_params = root / "broken-row-params.html"
        broken_params.write_text(re.sub(r"\sdata-params='[^']*'", "", prototype), encoding="utf-8")
        checked = subprocess.run(["node", str(checker), str(broken_params)], capture_output=True, text=True, check=False)
        require(checked.returncode != 0 and "记录上下文" in checked.stdout, "Interaction checker missed row navigation without params")
        payload_match = re.search(r'const PROTOTYPE_PAYLOAD = "([A-Za-z0-9+/=]+)"', final)
        require(payload_match is not None, "Final container prototype payload is missing")
        import base64
        embedded = base64.b64decode(payload_match.group(1)).decode("utf-8")
        require("const ANNOTATIONS = [];" in embedded, "Final container duplicated annotation data inside prototype")
        standalone = (output / "prototype.html").read_text(encoding="utf-8")
        require('"id":"create-entry"' in standalone, "Standalone prototype is missing annotation data")

        styled_output = root / "styled"
        styled = subprocess.run(
            [
                sys.executable, str(SKILL_ROOT / "scripts" / "build-project.py"), str(model_path),
                "--ui-profile", str(SKILL_ROOT / "assets" / "ui-profile-template.json"),
                "--output-dir", str(styled_output),
            ],
            capture_output=True, text=True, check=False,
        )
        require(styled.returncode == 0, styled.stdout + styled.stderr)
        styled_final = (styled_output / "visual-prd.html").read_text(encoding="utf-8")
        styled_source = (styled_output / "prototype-source.html").read_text(encoding="utf-8")
        require('id="ui-config-open"' in styled_final and "VisualPRDUIConfigurator" in styled_final, "UI configurator entry was not bundled")
        require("__VISUAL_PRD_UI_PROFILE_BASE64__" not in styled_final, "UI profile payload marker was not replaced")
        require("window.__vprdUiProfile" in styled_source and "data-ui-list-section" in styled_source, "Generated prototype lacks live UI profile hooks")
        require("describeUiProfile" in styled_source and "describe: pageId" in styled_source, "Generated prototype cannot report component locks to the configurator")
        require('<option value="compact">紧凑列表</option>' not in styled_final, "Configurator still conflates list structure with density")

        invalid_cases = []
        missing_action = json.loads(json.dumps(model_template, ensure_ascii=False))
        del missing_action["prototype"]["pages"][0]["components"][0]["actions"][0]["action"]
        invalid_cases.append(("missing-action", missing_action, "必须是非空字符串"))

        duplicate_tab = json.loads(json.dumps(model_template, ensure_ascii=False))
        duplicate_tab["prototype"]["pages"][1]["components"][0]["tabs"][1]["id"] = "overview"
        invalid_cases.append(("duplicate-tab", duplicate_tab, "Tab id 重复"))

        missing_field_name = json.loads(json.dumps(model_template, ensure_ascii=False))
        del missing_field_name["prototype"]["modals"][0]["fields"][0]["name"]
        invalid_cases.append(("missing-field-name", missing_field_name, "必须是非空字符串"))

        for name, invalid_model, expected_error in invalid_cases:
            invalid_path = root / f"{name}.json"
            invalid_path.write_text(json.dumps(invalid_model, ensure_ascii=False), encoding="utf-8")
            checked = subprocess.run(
                [sys.executable, str(SKILL_ROOT / "scripts/validate-model.py"), str(invalid_path)],
                capture_output=True, text=True, check=False,
            )
            require(checked.returncode != 0 and expected_error in checked.stderr, f"Invalid model case passed: {name}")


def validate_ui_profile_pipeline() -> None:
    profile = SKILL_ROOT / "assets" / "ui-profile-template.json"
    with tempfile.TemporaryDirectory(prefix="visual-prd-ui-") as temporary:
        root = Path(temporary)
        preview = root / "ui-profile-preview.html"
        check = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/validate-ui-profile.py"), str(profile)],
            capture_output=True, text=True, check=False,
        )
        require(check.returncode == 0, check.stdout + check.stderr)
        invalid_contrast = json.loads(profile.read_text(encoding="utf-8"))
        invalid_contrast["tokens"]["colors"]["brand"] = "#FFFFFF"
        invalid_contrast_path = root / "invalid-contrast.json"
        invalid_contrast_path.write_text(json.dumps(invalid_contrast, ensure_ascii=False), encoding="utf-8")
        rejected = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/validate-ui-profile.py"), str(invalid_contrast_path)],
            capture_output=True, text=True, check=False,
        )
        require(rejected.returncode != 0 and "对比度" in rejected.stderr, "Low-contrast UI profile was accepted")
        built = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/build-ui-preview.py"), str(profile), "--output", str(preview)],
            capture_output=True, text=True, check=False,
        )
        require(built.returncode == 0 and preview.is_file(), built.stdout + built.stderr)
        preview_source = preview.read_text(encoding="utf-8")
        require("主要操作" in preview_source and "错误字段" in preview_source and "暂无数据" in preview_source, "UI preview is missing required states")
        require("data-profile-path" in preview_source and "export-profile" in preview_source, "UI preview is not interactive")
        require(not re.search(r"(?:src|href)=[\"']https?://|@import|url\(\s*[\"']?https?://", preview_source, re.IGNORECASE), "UI preview contains an external resource")

        output = root / "dist"
        result = subprocess.run(
            [
                sys.executable, str(SKILL_ROOT / "scripts/build-project.py"),
                str(SKILL_ROOT / "assets/product-model-template.json"),
                "--ui-profile", str(profile), "--output-dir", str(output),
            ], capture_output=True, text=True, check=False,
        )
        require(result.returncode == 0, result.stdout + result.stderr)
        prototype = (output / "prototype-source.html").read_text(encoding="utf-8")
        require("filter-segmented" in prototype, "Configured filter variant was not compiled")
        require("--brand:#356AE6" in prototype, "Configured semantic color was not compiled")
        require((output / "ui-profile.json").is_file(), "Configured build did not preserve the UI profile source")
        require((output / "ui-profile-preview.html").is_file(), "Configured build did not emit the UI preview")

        overridden = json.loads(profile.read_text(encoding="utf-8"))
        overridden["page_overrides"] = {"list": {"components": {"list": {"variant": "cards"}, "filter": {"variant": "select"}}}}
        overridden_path = root / "page-overrides.json"
        overridden_path.write_text(json.dumps(overridden, ensure_ascii=False), encoding="utf-8")
        override_output = root / "overridden"
        override_build = subprocess.run(
            [
                sys.executable, str(SKILL_ROOT / "scripts/build-project.py"),
                str(SKILL_ROOT / "assets/product-model-template.json"),
                "--ui-profile", str(overridden_path), "--output-dir", str(override_output),
            ], capture_output=True, text=True, check=False,
        )
        require(override_build.returncode == 0, override_build.stdout + override_build.stderr)
        override_source = (override_output / "prototype-source.html").read_text(encoding="utf-8")
        require('data-ui-list-view="cards"' in override_source, "Page-level list override was not compiled")
        require('data-ui-filter-variant="select" data-filter="status" data-list-target="tasks"' in override_source, "Page-level filter override was not compiled")


def validate_project_modes() -> None:
    annotations = [{
        "id": "existing-anchor", "order": 1, "pageId": "existing",
        "title": "现有区域", "body": "保留原型并增加标注。", "businessRules": [],
        "scope": {"type": "page", "id": "existing"},
    }]
    with tempfile.TemporaryDirectory(prefix="visual-prd-modes-") as temporary:
        root = Path(temporary)
        prd = root / "prd.md"
        data = root / "annotations.json"
        existing = root / "existing.html"
        prd.write_text("# 现有需求\n", encoding="utf-8")
        data.write_text(json.dumps(annotations, ensure_ascii=False), encoding="utf-8")
        original = '<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body><main data-anno="existing-anchor">现有原型</main><script>window.existingRuntime=true;</script></body></html>'
        existing.write_text(original, encoding="utf-8")

        enhance_manifest = root / "enhance.json"
        enhance_manifest.write_text(json.dumps({
            "schema_version": "1.0", "mode": "enhance", "output_dir": "enhance-dist",
            "inputs": {"prd": "prd.md", "prototype": "existing.html", "annotations": "annotations.json"},
            "prototype": {"page_id": "existing"},
        }, ensure_ascii=False), encoding="utf-8")
        enhanced = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/build-review.py"), str(enhance_manifest)],
            capture_output=True, text=True, check=False,
        )
        require(enhanced.returncode == 0, enhanced.stdout + enhanced.stderr)
        require(existing.read_text(encoding="utf-8") == original, "Enhance mode modified the input prototype")
        enhanced_source = (root / "enhance-dist/prototype-source.html").read_text(encoding="utf-8")
        require("/*__ANNOTATION_RUNTIME__*/" in enhanced_source and "window.existingRuntime=true" in enhanced_source, "Enhance mode did not preserve and prepare the existing prototype")
        require("prototype-runtime.js" not in enhanced_source, "Enhance mode injected a second interaction runtime")

        assemble_manifest = root / "assemble.json"
        assemble_manifest.write_text(json.dumps({
            "schema_version": "1.0", "mode": "assemble", "output_dir": "assemble-dist",
            "inputs": {
                "prd": "prd.md", "prototype": "enhance-dist/prototype-source.html",
                "annotations": "annotations.json"
            },
        }, ensure_ascii=False), encoding="utf-8")
        assembled = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/build-review.py"), str(assemble_manifest)],
            capture_output=True, text=True, check=False,
        )
        require(assembled.returncode == 0, assembled.stdout + assembled.stderr)
        require((root / "assemble-dist/visual-prd.html").is_file(), "Assemble mode did not create the review container")

        generate_manifest = root / "generate.json"
        generate_manifest.write_text(json.dumps({
            "schema_version": "1.0", "mode": "generate", "output_dir": "generate-dist",
            "inputs": {
                "product_model": str(SKILL_ROOT / "assets/product-model-template.json"),
                "ui_profile": str(SKILL_ROOT / "assets/ui-profile-template.json")
            },
        }, ensure_ascii=False), encoding="utf-8")
        generated = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/build-review.py"), str(generate_manifest)],
            capture_output=True, text=True, check=False,
        )
        require(generated.returncode == 0, generated.stdout + generated.stderr)
        report = json.loads((root / "generate-dist/build-report.json").read_text(encoding="utf-8"))
        require(report.get("mode") == "generate" and report.get("project_manifest"), "Generate mode report lacks manifest provenance")
        require(report.get("status") == "PASS_STATIC" and report.get("manual_checks_remaining"), "Build report overstates unverified browser behavior")
        require(Path(report.get("primary_artifact", "")).resolve() == (root / "generate-dist/visual-prd.html").resolve(), "Build report does not identify the unique primary artifact")
        require(any(item.get("name") == "评审模式完整性" and item.get("status") == "PASS" for item in report.get("checks", [])), "Build report lacks review-mode validation")


def validate_metric_plan() -> None:
    template = json.loads((SKILL_ROOT / "assets/metric-plan-template.json").read_text(encoding="utf-8"))
    json.loads((SKILL_ROOT / "references/metrics.schema.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="visual-prd-metrics-") as temporary:
        root = Path(temporary)
        template["product"] = "目标管理"
        pending = root / "pending.json"
        pending.write_text(json.dumps(template, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts/validate-metrics.py"), str(pending)], capture_output=True, text=True)
        require(result.returncode == 0 and "UNVERIFIED" in result.stdout, "pending metrics were not identified")
        confirmed = {
            "schema_version": "1.0", "product": "目标管理", "applicability": "APPLICABLE",
            "applicability_reason": "需要衡量目标创建是否完成", "open_questions": [],
            "events": [{
                "id": "EVENT-001", "name": "goal_created", "trigger_condition": "创建目标成功并持久化后触发一次",
                "properties": [{"name": "goal_id", "type": "string", "required": True, "definition": "新建目标的唯一 ID"}],
                "acceptance_criteria": ["成功创建一次仅发送一次事件"], "status": "CONFIRMED",
            }],
            "metrics": [{
                "id": "METRIC-001", "name": "季度目标创建量", "product_goal": "团队完成季度目标设定",
                "calculation": {"type": "COUNT", "formula": "按季度去重统计成功创建的目标 ID", "numerator": "成功创建的目标 ID 数", "denominator": None},
                "window": "自然季度", "dedupe_rule": "按 goal_id 去重", "data_source": "目标创建事件表",
                "event_ids": ["EVENT-001"], "acceptance_criteria": ["与目标主表按 ID 核对一致"], "status": "CONFIRMED",
            }],
        }
        valid = root / "valid.json"
        valid.write_text(json.dumps(confirmed, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts/validate-metrics.py"), str(valid)], capture_output=True, text=True)
        require(result.returncode == 0 and "已确认 1 项" in result.stdout, result.stdout + result.stderr)
        confirmed["metrics"][0]["event_ids"] = ["EVENT-999"]
        invalid = root / "invalid.json"
        invalid.write_text(json.dumps(confirmed, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts/validate-metrics.py"), str(invalid)], capture_output=True, text=True)
        require(result.returncode != 0 and "未命中事件" in result.stderr, "broken metric-event link passed")


def validate_unannotated_existing_prototype() -> None:
    """A plain HTML prototype must never pass as an empty annotated review."""
    with tempfile.TemporaryDirectory(prefix="visual-prd-unannotated-") as temporary:
        root = Path(temporary)
        prd = root / "prd.md"
        prototype = root / "prototype.html"
        annotations = root / "annotations.json"
        manifest = root / "visual-prd.project.json"
        prd.write_text("# 原型观察记录（待产品确认）\n\n页面显示保存草稿按钮。\n", encoding="utf-8")
        prototype.write_text('<!doctype html><html><body><button id="save-draft">保存草稿</button></body></html>', encoding="utf-8")
        manifest.write_text(json.dumps({
            "schema_version": "1.0", "mode": "enhance", "output_dir": "dist",
            "inputs": {"prd": "prd.md", "prototype": "prototype.html", "annotations": "annotations.json"},
            "prototype": {"page_id": "edit"},
        }, ensure_ascii=False), encoding="utf-8")

        def build() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(SKILL_ROOT / "scripts/build-review.py"), str(manifest)],
                capture_output=True, text=True, check=False,
            )

        annotations.write_text("[]", encoding="utf-8")
        empty = build()
        require(empty.returncode != 0 and "为空" in empty.stderr, "zero annotations were accepted as a successful review")
        annotations.write_text(json.dumps([{
            "id": "save-draft", "order": 1, "pageId": "edit",
            "title": "保存草稿", "body": "页面显示保存草稿入口；保存结果待产品确认。",
            "businessRules": [], "scope": {"type": "page", "id": "edit"},
        }], ensure_ascii=False), encoding="utf-8")
        missing_anchor = build()
        require(missing_anchor.returncode != 0 and "data-anno" in missing_anchor.stderr, "missing prototype anchor did not fail clearly")
        prototype.write_text('<!doctype html><html><body><iframe id="mainFrame" src="about:blank"></iframe><script src="resources/scripts/player/axplayer.js"></script></body></html>', encoding="utf-8")
        axure_shell = build()
        require(axure_shell.returncode != 0 and "Axure 多文件" in axure_shell.stderr, "Axure entry shell was mistaken for a complete prototype")
        prototype.write_text('<!doctype html><html><body><button id="save-draft" data-anno="save-draft">保存草稿</button></body></html>', encoding="utf-8")
        completed = build()
        require(completed.returncode == 0, completed.stdout + completed.stderr)
        output = (root / "dist/prototype.html").read_text(encoding="utf-8")
        report = json.loads((root / "dist/build-report.json").read_text(encoding="utf-8"))
        require('data-anno="save-draft"' in output and "保存草稿" in output, "annotated result lacks the expected visible anchor or title")
        require(report.get("status") == "PASS_STATIC" and report.get("mode") == "enhance", "annotated existing prototype did not pass static build")
        final = (root / "dist/visual-prd.html").read_text(encoding="utf-8")
        resolver = re.search(r"pageId: \(\) => ([^\n]+),", final)
        require(resolver is not None, "final review is missing the prototype page resolver")
        route_test = (
            'const doc = {body: {dataset: {annoPage: "edit"}}};'
            'const state = {pageId: "home"};'
            f'const resolve = () => {resolver.group(1)};'
            'if (resolve() !== "edit") process.exit(1);'
            'doc.body.dataset.annoPage = "list";'
            'if (resolve() !== "list") process.exit(2);'
        )
        routed = subprocess.run(["node", "-e", route_test], capture_output=True, text=True, check=False)
        require(routed.returncode == 0, "prototype page resolver ignored the actual page: " + routed.stderr)


def validate_hygiene() -> None:
    junk = [path for path in SKILL_ROOT.rglob("*") if path.is_file() and path.name in IGNORED_SYSTEM_FILES]
    require(not junk, f"Remove system files before packaging: {', '.join(str(path.relative_to(SKILL_ROOT)) for path in junk)}")
    nested_archives = [path for path in SKILL_ROOT.rglob("*.zip") if path.is_file() and "releases" not in path.parts]
    require(not nested_archives, f"Remove nested archives from the Skill source: {', '.join(str(path.relative_to(SKILL_ROOT)) for path in nested_archives)}")


def main() -> None:
    missing = [name for name in REQUIRED_FILES if not (SKILL_ROOT / name).is_file()]
    require(not missing, f"Missing required files: {', '.join(missing)}")
    validate_hygiene()
    validate_frontmatter()
    validate_icon()
    validate_templates()
    validate_syntax()
    validate_smoke_build()
    validate_model_pipeline()
    validate_ui_profile_pipeline()
    validate_project_modes()
    validate_unannotated_existing_prototype()
    validate_metric_plan()
    flows = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts/check-flow-build.py")], capture_output=True, text=True, check=False)
    require(flows.returncode == 0, flows.stdout + flows.stderr)
    drafts = subprocess.run(["node", str(SKILL_ROOT / "scripts/check-draft-compatibility.js")], capture_output=True, text=True, check=False)
    require(drafts.returncode == 0, drafts.stdout + drafts.stderr)
    saves = subprocess.run(["node", str(SKILL_ROOT / "scripts/check-save-behavior.js")], capture_output=True, text=True, check=False)
    require(saves.returncode == 0, saves.stdout + saves.stderr)
    copy_edits = subprocess.run(["node", str(SKILL_ROOT / "scripts/check-prototype-text.js")], capture_output=True, text=True, check=False)
    require(copy_edits.returncode == 0, copy_edits.stdout + copy_edits.stderr)
    print(f"PASS: {SKILL_ROOT.name} is complete, self-contained, syntactically valid, and smoke-tested")


if __name__ == "__main__":
    main()
