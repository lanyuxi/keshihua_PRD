#!/usr/bin/env python3
"""Create an annotation-ready copy of an existing offline HTML prototype."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


RUNTIME_MARKER = "/*__ANNOTATION_RUNTIME__*/"
DATA_MARKER = "__ANNOTATION_DATA__"


def infer_page_id(annotations: list[dict], requested: str | None) -> str:
    if requested:
        return requested
    pages = sorted({str(item.get("pageId", "")).strip() for item in annotations if str(item.get("pageId", "")).strip() not in {"", "*"}})
    if len(pages) == 1:
        return pages[0]
    if not pages:
        return "page"
    raise ValueError("多页面原型必须在项目清单 prototype.page_id 中设置初始页面，并在切换时更新 body[data-anno-page]")


def prepare(source: str, annotations: list[dict], page_id: str | None = None) -> str:
    if not annotations:
        raise ValueError("标注数据为空；先按 references/bootstrap-existing.md 建立至少一条可核对标注")
    if re.search(r'<iframe\b[^>]*\bid\s*=\s*["\']mainFrame["\']', source, re.IGNORECASE) and "resources/scripts/player/axplayer.js" in source:
        raise ValueError("这是 Axure 多文件导出的入口壳；先查找目录内现有 visual-prd.project.json，或适配业务页及其资源，不能把 index.html/start.html 当成单文件原型装配")
    if RUNTIME_MARKER in source and DATA_MARKER in source:
        return source
    if RUNTIME_MARKER in source or DATA_MARKER in source:
        raise ValueError("原型只包含一个标注占位；必须同时包含运行时与数据占位")
    if not re.search(r"<html\b", source, re.IGNORECASE) or not re.search(r"</body\s*>", source, re.IGNORECASE):
        raise ValueError("增强模式要求完整 HTML 文档")

    anchors = set(re.findall(r'\bdata-anno\s*=\s*["\']([^"\']+)["\']', source, re.IGNORECASE))
    expected = {str(item.get("id", "")).strip() for item in annotations}
    if not anchors:
        raise ValueError("现有原型没有 data-anno 锚点；先按 references/bootstrap-existing.md 在工作副本的真实元素上添加锚点")
    missing = sorted(expected - anchors)
    if missing:
        raise ValueError("以下标注找不到原型锚点: " + ", ".join(missing) + "；请在工作副本中补齐对应 data-anno")

    initial_page = infer_page_id(annotations, page_id)
    body_match = re.search(r"<body\b([^>]*)>", source, re.IGNORECASE)
    if body_match and not re.search(r"\bdata-anno-page\s*=", body_match.group(0), re.IGNORECASE):
        replacement = body_match.group(0)[:-1] + f' data-anno-page="{initial_page}">'
        source = source[:body_match.start()] + replacement + source[body_match.end():]

    injection = f'''\n  <script>{RUNTIME_MARKER}</script>
  <script>
    const ANNOTATIONS = {DATA_MARKER};
    window.AnnotationRuntime.init({{
      annotations: ANNOTATIONS,
      pageId: () => document.body.dataset.annoPage || {json.dumps(initial_page, ensure_ascii=False)}
    }});
  </script>\n'''
    return re.sub(r"</body\s*>", lambda match: injection + match.group(0), source, count=1, flags=re.IGNORECASE)


def main() -> None:
    parser = argparse.ArgumentParser(description="为现有 HTML 原型生成标注增强副本")
    parser.add_argument("prototype", type=Path)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--page-id")
    parser.add_argument("--output", "-o", type=Path, required=True)
    args = parser.parse_args()
    try:
        annotations = json.loads(args.annotations.read_text(encoding="utf-8"))
        if not isinstance(annotations, list):
            raise ValueError("annotations 必须是数组")
        result = prepare(args.prototype.read_text(encoding="utf-8"), annotations, args.page_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"PASS: 已生成增强副本 {args.output}")


if __name__ == "__main__":
    main()
