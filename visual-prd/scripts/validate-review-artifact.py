#!/usr/bin/env python3
"""Validate the identity and mandatory modes of a Visual PRD review artifact."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED_MARKERS = {
    "标准容器身份": 'data-visual-prd-container="standard"',
    "左侧 PRD 区": 'class="panel left-panel"',
    "右侧标注区": 'class="panel right-panel"',
    "评审模式入口": 'data-review-mode-toggle',
    "浮动模式布局": '.floating-mode .workspace',
    "模式切换逻辑": 'function setMode(mode)',
    "三栏目标文案": '切换为三栏评审',
    "浮动目标文案": '切换为浮动标注',
}


def validate(source: str) -> list[str]:
    errors = [f"缺少{name}: {marker}" for name, marker in REQUIRED_MARKERS.items() if marker not in source]
    if not re.search(r'classList\.toggle\(["\']floating-mode["\']\s*,\s*floating\)', source):
        errors.append("模式切换没有控制 floating-mode 布局类")
    if not re.search(r'addEventListener\(["\']click["\']\s*,[^\n]+setMode', source):
        errors.append("评审模式入口没有绑定 setMode")
    if "left-panel" not in source or "right-panel" not in source or "resizer" not in source:
        errors.append("三栏容器结构不完整")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="验证可视化 PRD 主交付的容器身份与评审模式")
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        source = args.artifact.read_text(encoding="utf-8")
    except OSError as error:
        parser.error(str(error))
    errors = validate(source)
    if errors:
        parser.error("\n".join(errors))
    print(f"PASS: {args.artifact} 是标准主交付，三栏评审与浮动标注模式均存在")


if __name__ == "__main__":
    main()
