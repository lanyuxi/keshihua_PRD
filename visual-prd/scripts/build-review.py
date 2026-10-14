#!/usr/bin/env python3
"""Build a Visual PRD review from an assemble, enhance, or generate manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from project_manifest import load_manifest, resolved_inputs, resolve_path


SKILL_ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError((result.stdout + result.stderr).strip() or f"命令失败: {' '.join(command)}")
    return result.stdout.strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_if_needed(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def add_manifest_report(report_path: Path, mode: str, manifest_path: Path, inputs: dict[str, Path]) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    report.update({
        "mode": mode,
        "project_manifest": str(manifest_path),
        "inputs": {key: {"path": str(path), "sha256": digest(path)} for key, path in inputs.items()},
    })
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_generated(manifest_path: Path, manifest: dict, inputs: dict[str, Path], output: Path) -> None:
    command = [sys.executable, str(SKILL_ROOT / "scripts/build-project.py"), str(inputs["product_model"]), "--output-dir", str(output)]
    if "ui_profile" in inputs:
        command.extend(["--ui-profile", str(inputs["ui_profile"])])
    if "flows" in inputs:
        command.extend(["--flows", str(inputs["flows"])])
    run(command)
    annotations = json.loads((output / "annotations.json").read_text(encoding="utf-8"))
    if not isinstance(annotations, list) or not annotations:
        raise ValueError("生成结果没有标注；请先在产品模型中为需要评审的元素定义 annotation，不能交付空评审页")
    report_path = output / "build-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["primary_artifact"] = str(output / "visual-prd.html")
    report.setdefault("checks", []).append({
        "name": "评审模式完整性", "status": "PASS",
        "detail": run([sys.executable, str(SKILL_ROOT / "scripts/validate-review-artifact.py"), str(output / "visual-prd.html")]),
    })
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    add_manifest_report(output / "build-report.json", "generate", manifest_path, inputs)


def build_existing(manifest_path: Path, manifest: dict, inputs: dict[str, Path], output: Path) -> None:
    annotation_data = json.loads(inputs["annotations"].read_text(encoding="utf-8"))
    if not isinstance(annotation_data, list) or not annotation_data:
        raise ValueError("现有原型的 annotations.json 为空；请先按 references/bootstrap-existing.md 建立可核对的标注和 data-anno 锚点，不能把零标注页面当作构建成功")
    output.mkdir(parents=True, exist_ok=True)
    prd = output / "prd.md"
    annotations = output / "annotations.json"
    prototype_source = output / "prototype-source.html"
    copy_if_needed(inputs["prd"], prd)
    copy_if_needed(inputs["annotations"], annotations)

    if manifest["mode"] == "enhance":
        command = [
            sys.executable, str(SKILL_ROOT / "scripts/prepare-prototype.py"), str(inputs["prototype"]),
            "--annotations", str(inputs["annotations"]), "--output", str(prototype_source),
        ]
        page_id = (manifest.get("prototype") or {}).get("page_id")
        if page_id:
            command.extend(["--page-id", page_id])
        run(command)
    else:
        copy_if_needed(inputs["prototype"], prototype_source)

    checks = []
    source = prototype_source.read_text(encoding="utf-8")
    if "prototype-runtime.js" in source:
        checks.append({"name": "交互静态检查", "status": "PASS", "detail": run(["node", str(SKILL_ROOT / "scripts/check-interactions.js"), str(prototype_source)])})
    else:
        checks.append({"name": "交互静态检查", "status": "NOT_APPLICABLE", "detail": "原型保留自身交互运行时；需在浏览器验证关键流程"})

    build_command = [
        sys.executable, str(SKILL_ROOT / "scripts/build-container.py"),
        "--prototype", str(prototype_source), "--prd", str(prd), "--annotations", str(annotations),
        "--prototype-output", str(output / "prototype.html"), "--output", str(output / "visual-prd.html"),
    ]
    if "handoff" in inputs:
        build_command.extend(["--handoff", str(inputs["handoff"])])
    if "flows" in inputs:
        copy_if_needed(inputs["flows"], output / "flows.md")
        build_command.extend(["--flows", str(output / "flows.md")])
    run(build_command)
    checks.append({"name": "离线容器装配", "status": "PASS", "detail": "标注、原型与 PRD 已装配"})
    checks.append({
        "name": "评审模式完整性", "status": "PASS",
        "detail": run([sys.executable, str(SKILL_ROOT / "scripts/validate-review-artifact.py"), str(output / "visual-prd.html")]),
    })
    report = {
        "status": "PASS_STATIC", "mode": manifest["mode"], "project_manifest": str(manifest_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_artifact": str(output / "visual-prd.html"),
        "inputs": {key: {"path": str(path), "sha256": digest(path)} for key, path in inputs.items()},
        "artifacts": {name: str(output / name) for name in ("prd.md", "annotations.json", "prototype-source.html", "prototype.html", "visual-prd.html")},
        "checks": checks,
        "manual_checks_remaining": ["在真实浏览器验证原型关键流程与响应式布局", "确认标注定位准确且控制台无断言警告"],
    }
    (output / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="按项目清单构建可视化 PRD")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, help="覆盖项目清单中的输出目录")
    args = parser.parse_args()
    try:
        manifest_path = args.manifest.resolve()
        manifest = load_manifest(manifest_path)
        inputs = resolved_inputs(manifest_path, manifest)
        output = args.output_dir.resolve() if args.output_dir else resolve_path(manifest_path, manifest["output_dir"])
        if any(output == path for path in inputs.values()):
            raise ValueError("输出目录不能与输入文件相同")
        if manifest["mode"] == "generate":
            build_generated(manifest_path, manifest, inputs, output)
        else:
            build_existing(manifest_path, manifest, inputs, output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"PASS: {manifest['mode']} 模式已生成 {output / 'visual-prd.html'}")


if __name__ == "__main__":
    main()
