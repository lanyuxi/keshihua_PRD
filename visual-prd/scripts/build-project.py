#!/usr/bin/env python3
"""Build every Visual PRD artifact from one canonical product model."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError((result.stdout + result.stderr).strip() or f"命令失败: {' '.join(command)}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="从单一产品模型构建完整可视化 PRD")
    parser.add_argument("model", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ui-profile", type=Path, help="可选界面规范 JSON")
    parser.add_argument("--flows", type=Path, help="流程图 Markdown，包含 Mermaid 源码及文字说明")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scripts = SKILL_ROOT / "scripts"
    files = {
        "prd": output / "prd.md",
        "annotations": output / "annotations.json",
        "prototype_source": output / "prototype-source.html",
        "prototype": output / "prototype.html",
        "visual_prd": output / "visual-prd.html",
        "report": output / "build-report.json",
    }
    if args.ui_profile:
        files["ui_profile"] = output / "ui-profile.json"
        files["ui_preview"] = output / "ui-profile-preview.html"
    if args.flows:
        files["flows"] = output / "flows.md"
    checks: list[dict] = []
    try:
        checks.append({"name": "产品模型", "status": "PASS", "detail": run([sys.executable, str(scripts / "validate-model.py"), str(args.model)])})
        run([sys.executable, str(scripts / "render-prd.py"), str(args.model), "-o", str(files["prd"])])
        run([sys.executable, str(scripts / "build-annotations.py"), str(args.model), "-o", str(files["annotations"])])
        prototype_command = [sys.executable, str(scripts / "build-prototype.py"), str(args.model), "-o", str(files["prototype_source"])]
        if args.ui_profile:
            checks.append({"name": "界面规范", "status": "PASS", "detail": run([sys.executable, str(scripts / "validate-ui-profile.py"), str(args.ui_profile)])})
            if args.ui_profile.resolve() != files["ui_profile"].resolve():
                shutil.copy2(args.ui_profile, files["ui_profile"])
            prototype_command.extend(["--ui-profile", str(args.ui_profile)])
            run([sys.executable, str(scripts / "build-ui-preview.py"), str(args.ui_profile), "--output", str(files["ui_preview"])])
        run(prototype_command)
        checks.append({"name": "交互静态检查", "status": "PASS", "detail": run(["node", str(scripts / "check-interactions.js"), str(files["prototype_source"])])})
        checks.append({"name": "生成行为检查", "status": "PASS", "detail": run(["node", str(scripts / "check-generated-behavior.js"), str(files["prototype_source"])])})
        container_command = [
            sys.executable, str(scripts / "build-container.py"),
            "--prototype", str(files["prototype_source"]),
            "--prd", str(files["prd"]),
            "--annotations", str(files["annotations"]),
            "--prototype-output", str(files["prototype"]),
            "--output", str(files["visual_prd"]),
        ]
        if args.ui_profile:
            container_command.extend(["--ui-profile", str(args.ui_profile)])
        if args.flows:
            if args.flows.resolve() != files["flows"].resolve():
                shutil.copy2(args.flows, files["flows"])
            container_command.extend(["--flows", str(files["flows"])])
        checks.append({"name": "离线容器装配", "status": "PASS", "detail": run(container_command)})
        checks.append({
            "name": "评审模式完整性", "status": "PASS",
            "detail": run([sys.executable, str(scripts / "validate-review-artifact.py"), str(files["visual_prd"])]),
        })
    except (OSError, ValueError) as error:
        checks.append({"name": "构建", "status": "FAIL", "detail": str(error)})
        report = {"status": "FAIL", "model": str(args.model.resolve()), "generated_at": datetime.now(timezone.utc).isoformat(), "checks": checks}
        files["report"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        parser.error(str(error))

    report = {
        "status": "PASS_STATIC",
        "model": str(args.model.resolve()),
        "ui_profile": str(args.ui_profile.resolve()) if args.ui_profile else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_artifact": str(files["visual_prd"]),
        "artifacts": {name: str(path) for name, path in files.items() if name != "report"},
        "checks": checks,
        "manual_checks_remaining": ["在浏览器中验证关键流程、响应式布局和标注定位", "确认控制台无编号不一致警告"],
    }
    files["report"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: 已从单一产品模型生成完整交付物：{files['visual_prd']}")
    print(f"报告: {files['report']}")


if __name__ == "__main__":
    main()
