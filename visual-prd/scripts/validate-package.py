#!/usr/bin/env python3
"""Validate that the Visual PRD skill package is portable and self-contained."""

from __future__ import annotations

import re
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
    "references/editing-and-export.md",
    "assets/container-template.html",
    "assets/mermaid.min.js",
    "assets/mermaid-LICENSE.txt",
    "assets/container-styles.css",
    "assets/prototype-template.html",
    "scripts/build-container.py",
    "scripts/check-interactions.js",
    "scripts/prototype-runtime.js",
    "scripts/annotation-runtime.js",
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


def validate_templates() -> None:
    prototype = (SKILL_ROOT / "assets/prototype-template.html").read_text(encoding="utf-8")
    container = (SKILL_ROOT / "assets/container-template.html").read_text(encoding="utf-8")
    for marker in ("/*__ANNOTATION_RUNTIME__*/", "__ANNOTATION_DATA__", "prototype-runtime.js"):
        require(marker in prototype, f"Prototype template is missing {marker}")
    for marker in (
        "__VISUAL_PRD_PROTOTYPE_BASE64__",
        "__VISUAL_PRD_PRD_MARKDOWN_BASE64__",
        "__VISUAL_PRD_ANNOTATIONS_BASE64__",
        "__VISUAL_PRD_DEVELOPER_BASE64__",
        "__VISUAL_PRD_FLOWS_BASE64__",
        "/*__MERMAID_RUNTIME__*/",
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
    for name in ("build-container.py", "package-skill.py", "validate-package.py"):
        source = (SKILL_ROOT / "scripts" / name).read_text(encoding="utf-8")
        compile(source, f"scripts/{name}", "exec")
    container = (SKILL_ROOT / "assets/container-template.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", container, re.DOTALL)
    for script in scripts:
        result = subprocess.run(["node", "--check", "-"], input=script, capture_output=True, text=True)
        require(result.returncode == 0, result.stderr or "Container JavaScript syntax check failed")
    for name in ("check-interactions.js", "prototype-runtime.js", "annotation-runtime.js", "../assets/mermaid.min.js"):
        result = subprocess.run(
            ["node", "--check", str(SKILL_ROOT / "scripts" / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        require(result.returncode == 0, result.stderr.strip() or f"JavaScript syntax check failed: {name}")


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


def validate_hygiene() -> None:
    junk = [path for path in SKILL_ROOT.rglob("*") if path.is_file() and path.name in IGNORED_SYSTEM_FILES]
    require(not junk, f"Remove system files before packaging: {', '.join(str(path.relative_to(SKILL_ROOT)) for path in junk)}")


def main() -> None:
    missing = [name for name in REQUIRED_FILES if not (SKILL_ROOT / name).is_file()]
    require(not missing, f"Missing required files: {', '.join(missing)}")
    validate_hygiene()
    validate_frontmatter()
    validate_templates()
    validate_syntax()
    validate_smoke_build()
    print(f"PASS: {SKILL_ROOT.name} is complete, self-contained, syntactically valid, and smoke-tested")


if __name__ == "__main__":
    main()
