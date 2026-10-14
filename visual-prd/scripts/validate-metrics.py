#!/usr/bin/env python3
"""Validate a standalone metric and event plan without external libraries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


METRIC_ID = re.compile(r"^METRIC-[0-9]{3,}$")
EVENT_ID = re.compile(r"^EVENT-[0-9]{3,}$")
PROPERTY_TYPES = {"string", "number", "boolean", "timestamp"}
CALCULATION_TYPES = {"COUNT", "SUM", "RATIO", "CUSTOM"}


def filled(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip() != "待确认"


def string_list(value: object, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        errors.append(f"{label} 必须是非空字符串组成的数组")
        return []
    return value


def validate(plan: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["顶层必须是 JSON 对象"]
    if plan.get("schema_version") != "1.0":
        errors.append("schema_version 必须为 1.0")
    if not filled(plan.get("product")):
        errors.append("product 必须填写产品名称")
    applicability = plan.get("applicability")
    if applicability not in {"APPLICABLE", "NOT_APPLICABLE", "PENDING"}:
        errors.append("applicability 必须为 APPLICABLE、NOT_APPLICABLE 或 PENDING")
    if not filled(plan.get("applicability_reason")):
        errors.append("applicability_reason 必须说明选择依据")
    metrics = plan.get("metrics")
    events = plan.get("events")
    if not isinstance(metrics, list):
        errors.append("metrics 必须是数组")
        metrics = []
    if not isinstance(events, list):
        errors.append("events 必须是数组")
        events = []
    questions = string_list(plan.get("open_questions"), "open_questions", errors)
    if applicability == "NOT_APPLICABLE" and (metrics or events):
        errors.append("NOT_APPLICABLE 时不得定义指标或事件")
    if applicability == "APPLICABLE" and not metrics and not questions:
        errors.append("APPLICABLE 时至少定义一个指标或写明待确认问题")
    if applicability == "PENDING" and not questions:
        errors.append("PENDING 时必须写明待确认问题")

    event_ids: set[str] = set()
    event_names: set[str] = set()
    pending = False
    for index, event in enumerate(events):
        label = f"events[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{label} 必须是对象")
            continue
        event_id = event.get("id")
        if not isinstance(event_id, str) or not EVENT_ID.fullmatch(event_id):
            errors.append(f"{label}.id 必须是 EVENT-###")
        elif event_id in event_ids:
            errors.append(f"事件 ID 重复：{event_id}")
        else:
            event_ids.add(event_id)
        name = event.get("name")
        if not filled(name):
            errors.append(f"{label}.name 不能为空")
        elif name in event_names:
            errors.append(f"事件名称重复：{name}")
        else:
            event_names.add(name)
        status = event.get("status")
        if status not in {"CONFIRMED", "PENDING"}:
            errors.append(f"{label}.status 无效")
        elif status == "PENDING":
            pending = True
        if status == "CONFIRMED" and not filled(event.get("trigger_condition")):
            errors.append(f"{label} 已确认但缺少准确触发条件")
        if not isinstance(event.get("trigger_condition"), str):
            errors.append(f"{label}.trigger_condition 必须是字符串")
        if "prototype_anchor" in event and not isinstance(event["prototype_anchor"], str):
            errors.append(f"{label}.prototype_anchor 必须是字符串")
        criteria = string_list(event.get("acceptance_criteria"), f"{label}.acceptance_criteria", errors)
        if status == "CONFIRMED" and not criteria:
            errors.append(f"{label} 已确认但缺少埋点验收条件")
        properties = event.get("properties")
        if not isinstance(properties, list):
            errors.append(f"{label}.properties 必须是数组")
            continue
        property_names: set[str] = set()
        for property_index, prop in enumerate(properties):
            prop_label = f"{label}.properties[{property_index}]"
            if not isinstance(prop, dict):
                errors.append(f"{prop_label} 必须是对象")
                continue
            prop_name = prop.get("name")
            if not filled(prop_name):
                errors.append(f"{prop_label}.name 不能为空")
            elif prop_name in property_names:
                errors.append(f"{label} 属性名称重复：{prop_name}")
            else:
                property_names.add(prop_name)
            if prop.get("type") not in PROPERTY_TYPES:
                errors.append(f"{prop_label}.type 无效")
            if not isinstance(prop.get("required"), bool):
                errors.append(f"{prop_label}.required 必须是布尔值")
            if not filled(prop.get("definition")):
                errors.append(f"{prop_label}.definition 必须说明取值含义")

    metric_ids: set[str] = set()
    for index, metric in enumerate(metrics):
        label = f"metrics[{index}]"
        if not isinstance(metric, dict):
            errors.append(f"{label} 必须是对象")
            continue
        metric_id = metric.get("id")
        if not isinstance(metric_id, str) or not METRIC_ID.fullmatch(metric_id):
            errors.append(f"{label}.id 必须是 METRIC-###")
        elif metric_id in metric_ids:
            errors.append(f"指标 ID 重复：{metric_id}")
        else:
            metric_ids.add(metric_id)
        for key in ("name", "product_goal"):
            if not filled(metric.get(key)):
                errors.append(f"{label}.{key} 不能为空")
        status = metric.get("status")
        if status not in {"CONFIRMED", "PENDING"}:
            errors.append(f"{label}.status 无效")
        elif status == "PENDING":
            pending = True
        calculation = metric.get("calculation")
        if not isinstance(calculation, dict):
            errors.append(f"{label}.calculation 必须是对象")
            calculation = {}
        calc_type = calculation.get("type")
        if calc_type not in CALCULATION_TYPES:
            errors.append(f"{label}.calculation.type 无效")
        denominator = calculation.get("denominator")
        if denominator is not None and not isinstance(denominator, str):
            errors.append(f"{label}.calculation.denominator 必须是字符串或 null")
        if calc_type == "RATIO" and status == "CONFIRMED" and not filled(denominator):
            errors.append(f"{label} 已确认的比率指标必须定义分母")
        if calc_type != "RATIO" and denominator is not None:
            errors.append(f"{label} 非比率指标的分母必须为 null")
        if status == "CONFIRMED":
            for key in ("formula", "numerator"):
                if not filled(calculation.get(key)):
                    errors.append(f"{label}.calculation.{key} 未确认")
            for key in ("window", "dedupe_rule", "data_source"):
                if not filled(metric.get(key)):
                    errors.append(f"{label}.{key} 未确认")
        for key in ("formula", "numerator"):
            if not isinstance(calculation.get(key), str):
                errors.append(f"{label}.calculation.{key} 必须是字符串")
        for key in ("window", "dedupe_rule", "data_source"):
            if not isinstance(metric.get(key), str):
                errors.append(f"{label}.{key} 必须是字符串")
        refs = string_list(metric.get("event_ids"), f"{label}.event_ids", errors)
        if len(refs) != len(set(refs)):
            errors.append(f"{label}.event_ids 不得重复")
        for ref in refs:
            if ref not in event_ids:
                errors.append(f"{label}.event_ids 未命中事件：{ref}")
        criteria = string_list(metric.get("acceptance_criteria"), f"{label}.acceptance_criteria", errors)
        if status == "CONFIRMED" and not criteria:
            errors.append(f"{label} 已确认但缺少指标验收条件")
    if pending and not questions:
        errors.append("存在待确认指标或事件时，open_questions 不得为空")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate metric and tracking definitions.")
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"FAIL: 无法读取指标文件：{error}", file=sys.stderr)
        raise SystemExit(1)
    errors = validate(plan)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
    confirmed = sum(item.get("status") == "CONFIRMED" for item in plan["metrics"] if isinstance(item, dict))
    print(f"PASS: 指标定义有效；已确认 {confirmed} 项，总计 {len(plan['metrics'])} 项")
    if plan["applicability"] == "PENDING" or any(item.get("status") == "PENDING" for item in plan["metrics"] + plan["events"] if isinstance(item, dict)):
        print("UNVERIFIED: 尚有待确认指标、事件或适用性，不得宣称数据已可计算")


if __name__ == "__main__":
    main()
