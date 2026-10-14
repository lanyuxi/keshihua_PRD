#!/usr/bin/env python3
"""Render PRD Markdown deterministically from the canonical product model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_core import load_model, validate_model


def render(model: dict) -> str:
    index = validate_model(model)
    product = model["product"]
    lines = [
        f"# {product['name']} 产品需求文档",
        "",
        "## 1. 产品定型",
        "",
        product["summary"],
        "",
        f"**产品目标：** {product['goal']}",
        "",
        f"**目标平台：** {'、'.join(product.get('platforms') or ['待确认'])}",
        "",
        "### 范围内",
        "",
        *([f"- {item}" for item in product.get("scope", [])] or ["- 待确认"]),
        "",
        "### 范围外",
        "",
        *([f"- {item}" for item in product.get("exclusions", [])] or ["- 待确认"]),
        "",
        "## 2. 功能板块与依赖",
        "",
        "| 优先级 | 板块 | 依赖 |",
        "| --- | --- | --- |",
    ]
    for module in model["modules"]:
        dependencies = "、".join(index["modules"][item]["title"] for item in module.get("dependencies", [])) or "无"
        lines.append(f"| {module.get('priority', 'P1')} | {module['title']} | {dependencies} |")

    lines.extend(["", "## 3. 角色与权限", ""])
    for role in model["roles"]:
        lines.extend([f"### {role['name']}", "", role.get("description", ""), ""])
        lines.extend([f"- {item}" for item in role.get("permissions", [])] or ["- 待确认"])
        lines.append("")

    lines.extend(["## 4. 功能需求", ""])
    for module in model["modules"]:
        lines.extend([f"### {module['title']}", "", module.get("description", ""), ""])
        module_requirements = [index["requirements"][item] for item in module.get("requirement_ids", [])]
        for requirement in module_requirements:
            lines.extend([
                f"#### {requirement['id']} · {requirement['title']}",
                "",
                requirement["description"],
                "",
                "**用户故事**",
                "",
            ])
            for story in requirement.get("user_stories", []):
                role = index["roles"][story["role_id"]]["name"]
                lines.append(f"- 作为{role}，{story['text']}")
            lines.extend(["", "**业务规则**", ""])
            for rule_id in requirement.get("rule_ids", []):
                rule = index["rules"][rule_id]
                suffix = "（待确认）" if rule["status"] == "PENDING" else ""
                lines.append(f"- `{rule_id}` {rule['text']}{suffix}")
            if not requirement.get("rule_ids"):
                lines.append("- 无")
            machine = requirement.get("state_machine")
            if machine:
                lines.extend(["", "**状态机**", "", "| 当前状态 | 操作 | 下一状态 | 执行角色 |", "| --- | --- | --- | --- |"])
                for transition in machine.get("transitions", []):
                    actor = index["roles"].get(transition.get("actor_role_id"), {}).get("name", "系统")
                    lines.append(f"| {transition.get('from', '')} | {transition.get('action', '')} | {transition.get('to', '')} | {actor} |")
            lines.extend(["", "**验收条件**", ""])
            for criterion_id in requirement.get("acceptance_ids", []):
                criterion = index["criteria"][criterion_id]
                suffix = "（待确认）" if criterion["status"] == "PENDING" else ""
                lines.append(f"- [ ] `{criterion_id}` {criterion['text']}{suffix}")
            if not requirement.get("acceptance_ids"):
                lines.append("- [ ] 待补充")
            lines.append("")

    lines.extend(["## 5. 待确认事项", ""])
    questions = model.get("open_questions", [])
    if questions:
        for question in questions:
            refs = "、".join(question.get("requirement_ids", []))
            lines.append(f"- `{question.get('id', 'Q')}` {question.get('question', '')}{f'（关联：{refs}）' if refs else ''}")
    else:
        lines.append("- 无")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="从产品模型生成 PRD Markdown")
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", "-o", type=Path, required=True)
    args = parser.parse_args()
    try:
        content = render(load_model(args.model))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"PASS: 已生成 {args.output}")


if __name__ == "__main__":
    main()
