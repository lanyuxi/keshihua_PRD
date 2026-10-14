#!/usr/bin/env python3
"""Shared validation and traversal helpers for the Visual PRD product model."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
VALID_STATUSES = {"CONFIRMED", "PENDING"}
VALID_SCOPES = {"page", "tab", "drawer", "modal"}
VALID_COMPONENTS = {"hero", "stats", "table", "tabs", "cards", "timeline", "text", "custom"}
VALID_ACTION_STYLES = {"primary", "secondary", "ghost", "danger"}
VALID_FILTER_VARIANTS = {"select", "segmented", "chips"}
VALID_LIST_VARIANTS = {"table", "compact", "cards"}
VALID_DENSITIES = {"comfortable", "compact"}
VALID_TAB_VARIANTS = {"underline", "pills", "segmented"}
VALID_DIALOG_SIZES = {"small", "medium", "large"}
VALID_FIELD_TYPES = {"text", "email", "number", "date", "datetime-local", "textarea", "select"}
VALID_SUBMIT_OPERATIONS = {"save", "append"}


def load_model(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("产品模型根节点必须是 JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_text(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{label} 必须是非空字符串")
    return value.strip()


def require_id(value: Any, label: str) -> str:
    identifier = require_text(value, label)
    require(bool(IDENTIFIER.fullmatch(identifier)), f"{label} 只能包含英文字母、数字、短横线和下划线，且以字母开头")
    return identifier


def as_list(value: Any, label: str) -> list[Any]:
    require(isinstance(value, list), f"{label} 必须是数组")
    return value


def unique_index(items: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        require(isinstance(item, dict), f"{label}[{index}] 必须是 object")
        identifier = require_id(item.get("id"), f"{label}[{index}].id")
        require(identifier not in result, f"{label} 出现重复 id: {identifier}")
        result[identifier] = item
    return result


def validate_action_command(
    command: Any,
    label: str,
    pages: dict[str, dict[str, Any]],
    modals: dict[str, dict[str, Any]],
) -> str:
    value = require_text(command, label)
    if value == "close-modal":
        return value
    action_type, separator, payload = value.partition(":")
    require(bool(separator), f"{label} 必须使用 type:payload 格式")
    if action_type == "navigate":
        require(payload in pages, f"{label} 引用了不存在的页面 {payload}")
    elif action_type == "open-modal":
        require(payload in modals, f"{label} 引用了不存在的弹层 {payload}")
    elif action_type == "set-state":
        key, equals, _ = payload.partition("=")
        require(bool(equals) and bool(key.strip()), f"{label} 的 set-state 缺少状态 key 或值")
    elif action_type == "toggle":
        require(bool(payload.strip()), f"{label} 的 toggle 缺少状态 key")
    else:
        raise ValueError(f"{label} 使用了不受支持的 action 类型 {action_type}")
    return value


def iter_annotated_nodes(model: dict[str, Any]):
    prototype = model.get("prototype") or {}
    if prototype.get("navigation_annotation"):
        yield prototype, prototype.get("navigation_annotation"), "*", "prototype.navigation_annotation"
    for page in prototype.get("pages") or []:
        yield page, page.get("annotation"), page.get("id"), f'prototype.pages[{page.get("id", "?")}]'
        for component_index, component in enumerate(page.get("components") or []):
            yield component, component.get("annotation"), page.get("id"), f'page {page.get("id")}.components[{component_index}]'
            for action_index, action in enumerate(component.get("actions") or []):
                yield action, action.get("annotation"), page.get("id"), f'page {page.get("id")}.actions[{action_index}]'
            for row_index, row in enumerate(component.get("rows") or []):
                if isinstance(row, dict):
                    yield row, row.get("annotation"), page.get("id"), f'page {page.get("id")}.rows[{row_index}]'
            for tab_index, tab in enumerate(component.get("tabs") or []):
                if isinstance(tab, dict):
                    yield tab, tab.get("annotation"), page.get("id"), f'page {page.get("id")}.tabs[{tab_index}]'
    for modal in prototype.get("modals") or []:
        page_id = modal.get("page_id") or "*"
        yield modal, modal.get("annotation"), page_id, f'prototype.modals[{modal.get("id", "?")}]'
        for field_index, field in enumerate(modal.get("fields") or []):
            if isinstance(field, dict):
                yield field, field.get("annotation"), page_id, f'modal {modal.get("id")}.fields[{field_index}]'


def validate_model(model: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    require(model.get("schema_version") == "1.0", "schema_version 必须为 1.0")
    product = model.get("product")
    require(isinstance(product, dict), "product 必须是 object")
    for key in ("name", "summary", "goal"):
        require_text(product.get(key), f"product.{key}")
    for key in ("platforms", "scope", "exclusions"):
        values = as_list(product.get(key, []), f"product.{key}")
        require(all(isinstance(item, str) for item in values), f"product.{key} 只能包含字符串")

    roles = unique_index(as_list(model.get("roles", []), "roles"), "roles")
    modules = unique_index(as_list(model.get("modules", []), "modules"), "modules")
    rules = unique_index(as_list(model.get("rules", []), "rules"), "rules")
    criteria = unique_index(as_list(model.get("acceptance_criteria", []), "acceptance_criteria"), "acceptance_criteria")
    requirements = unique_index(as_list(model.get("requirements", []), "requirements"), "requirements")

    for identifier, item in roles.items():
        require_text(item.get("name"), f"roles.{identifier}.name")
        require(isinstance(item.get("permissions", []), list), f"roles.{identifier}.permissions 必须是数组")
    for identifier, item in modules.items():
        require_text(item.get("title"), f"modules.{identifier}.title")
        require(item.get("priority", "P1") in VALID_PRIORITIES, f"modules.{identifier}.priority 无效")
        for dependency in item.get("dependencies", []):
            require(dependency in modules, f"modules.{identifier} 引用了不存在的依赖 {dependency}")
        for requirement_id in item.get("requirement_ids", []):
            require(requirement_id in requirements, f"modules.{identifier} 引用了不存在的需求 {requirement_id}")
    for identifier, item in rules.items():
        require_text(item.get("text"), f"rules.{identifier}.text")
        require(item.get("status") in VALID_STATUSES, f"rules.{identifier}.status 无效")
    for identifier, item in criteria.items():
        require_text(item.get("text"), f"acceptance_criteria.{identifier}.text")
        require(item.get("status") in VALID_STATUSES, f"acceptance_criteria.{identifier}.status 无效")
        require(item.get("requirement_id") in requirements, f"acceptance_criteria.{identifier} 引用了不存在的需求")
    for identifier, item in requirements.items():
        require_text(item.get("title"), f"requirements.{identifier}.title")
        require_text(item.get("description"), f"requirements.{identifier}.description")
        require(item.get("module_id") in modules, f"requirements.{identifier} 引用了不存在的模块")
        for role_story in item.get("user_stories", []):
            require(isinstance(role_story, dict), f"requirements.{identifier}.user_stories 必须为 object 数组")
            require(role_story.get("role_id") in roles, f"requirements.{identifier} 用户故事引用了不存在的角色")
            require_text(role_story.get("text"), f"requirements.{identifier}.user_stories.text")
        for rule_id in item.get("rule_ids", []):
            require(rule_id in rules, f"requirements.{identifier} 引用了不存在的规则 {rule_id}")
        for criterion_id in item.get("acceptance_ids", []):
            require(criterion_id in criteria, f"requirements.{identifier} 引用了不存在的验收条件 {criterion_id}")

    prototype = model.get("prototype")
    require(isinstance(prototype, dict), "prototype 必须是 object")
    require(isinstance(prototype.get("initial_state", {}), dict), "prototype.initial_state 必须是 object")
    pages = unique_index(as_list(prototype.get("pages", []), "prototype.pages"), "prototype.pages")
    modals = unique_index(as_list(prototype.get("modals", []), "prototype.modals"), "prototype.modals")
    require(bool(pages), "prototype.pages 至少包含一个页面")
    list_ids: set[str] = set()
    list_columns: dict[str, set[str]] = {}
    for page_id, page in pages.items():
        for index, component in enumerate(as_list(page.get("components", []), f"prototype.pages.{page_id}.components")):
            if isinstance(component, dict) and component.get("type") == "table":
                list_id = require_id(component.get("list_id", component.get("id")), f"页面 {page_id} 的列表组件 {index}.list_id")
                require(list_id not in list_ids, f"列表 id 重复: {list_id}")
                list_ids.add(list_id)
                list_columns[list_id] = {
                    str(column.get("key")) for column in component.get("columns", [])
                    if isinstance(column, dict) and column.get("key")
                }
    for identifier, page in pages.items():
        require_text(page.get("title"), f"prototype.pages.{identifier}.title")
        for requirement_id in page.get("requirement_ids", []):
            require(requirement_id in requirements, f"页面 {identifier} 引用了不存在的需求 {requirement_id}")
        components = as_list(page.get("components", []), f"prototype.pages.{identifier}.components")
        for index, component in enumerate(components):
            require(isinstance(component, dict), f"页面 {identifier} 的组件 {index} 必须是 object")
            require(component.get("type") in VALID_COMPONENTS, f"页面 {identifier} 的组件 {index} 类型不受支持")
            appearance = component.get("appearance", {})
            require(isinstance(appearance, dict), f"页面 {identifier} 的组件 {index}.appearance 必须是 object")
            if component.get("type") == "table":
                require(not (set(appearance) - {"variant", "density", "filter_variant"}), f"页面 {identifier} 的列表组件 appearance 存在未知字段")
                require(appearance.get("variant", "table") in VALID_LIST_VARIANTS, f"页面 {identifier} 的列表组件 variant 无效")
                require(appearance.get("density", "comfortable") in VALID_DENSITIES, f"页面 {identifier} 的列表组件 density 无效")
                require(appearance.get("filter_variant", "select") in VALID_FILTER_VARIANTS, f"页面 {identifier} 的筛选器 variant 无效")
                columns = as_list(component.get("columns", []), f"页面 {identifier} 的列表组件 columns")
                column_keys: set[str] = set()
                for column_index, column in enumerate(columns):
                    require(isinstance(column, dict), f"页面 {identifier} 的列表列 {column_index} 必须是 object")
                    key = require_id(column.get("key"), f"页面 {identifier} 的列表列 {column_index}.key")
                    require(key not in column_keys, f"页面 {identifier} 的列表列 key 重复: {key}")
                    column_keys.add(key)
                    require_text(column.get("label"), f"页面 {identifier} 的列表列 {key}.label")
                rows = as_list(component.get("rows", []), f"页面 {identifier} 的列表组件 rows")
                row_ids: set[str] = set()
                for row_index, row in enumerate(rows):
                    require(isinstance(row, dict), f"页面 {identifier} 的列表行 {row_index} 必须是 object")
                    row_id = require_id(row.get("id"), f"页面 {identifier} 的列表行 {row_index}.id")
                    require(row_id not in row_ids, f"页面 {identifier} 的列表行 id 重复: {row_id}")
                    row_ids.add(row_id)
                    missing_columns = [key for key in column_keys if key not in row]
                    require(not missing_columns, f"页面 {identifier} 的列表行 {row_id} 缺少字段: {', '.join(sorted(missing_columns))}")
                controls = component.get("controls", {})
                require(isinstance(controls, dict), f"页面 {identifier} 的列表 controls 必须是 object")
                for filter_index, filter_spec in enumerate(controls.get("filters", [])):
                    require(isinstance(filter_spec, dict), f"页面 {identifier} 的筛选器 {filter_index} 必须是 object")
                    filter_key = require_id(filter_spec.get("key"), f"页面 {identifier} 的筛选器 {filter_index}.key")
                    require(filter_key in column_keys, f"页面 {identifier} 的筛选字段 {filter_key} 不在列表列中")
                    options = as_list(filter_spec.get("options", []), f"页面 {identifier} 的筛选器 {filter_key}.options")
                    require(all(isinstance(option, dict) and "value" in option for option in options), f"页面 {identifier} 的筛选器 {filter_key} 选项无效")
                if component.get("row_action") is not None:
                    validate_action_command(component.get("row_action"), f"页面 {identifier} 的列表 row_action", pages, modals)
                    row_params = component.get("row_params", {"id": "{id}"})
                    require(isinstance(row_params, dict) and bool(row_params), f"页面 {identifier} 的列表 row_params 必须是非空 object")
                    require(all(isinstance(key, str) and key and isinstance(value, (str, int, float, bool)) for key, value in row_params.items()), f"页面 {identifier} 的列表 row_params 只能包含标量模板")
            elif component.get("type") == "tabs":
                require(not (set(appearance) - {"variant"}), f"页面 {identifier} 的 Tab appearance 存在未知字段")
                require(appearance.get("variant", "underline") in VALID_TAB_VARIANTS, f"页面 {identifier} 的 Tab variant 无效")
                tabs = as_list(component.get("tabs", []), f"页面 {identifier} 的 tabs")
                require(bool(tabs), f"页面 {identifier} 的 Tab 组件至少包含一个 Tab")
                tab_ids: set[str] = set()
                for tab_index, tab in enumerate(tabs):
                    require(isinstance(tab, dict), f"页面 {identifier} 的 Tab {tab_index} 必须是 object")
                    tab_id = require_id(tab.get("id"), f"页面 {identifier} 的 Tab {tab_index}.id")
                    require(tab_id not in tab_ids, f"页面 {identifier} 的 Tab id 重复: {tab_id}")
                    tab_ids.add(tab_id)
                    require_text(tab.get("label"), f"页面 {identifier} 的 Tab {tab_id}.label")
            else:
                require(not appearance, f"页面 {identifier} 的 {component.get('type')} 组件暂不支持 appearance")
            for action_index, action in enumerate(component.get("actions", [])):
                require(isinstance(action, dict), f"页面 {identifier} 的 action {action_index} 必须是 object")
                require_text(action.get("label"), f"页面 {identifier} 的 action {action_index}.label")
                validate_action_command(action.get("action"), f"页面 {identifier} 的 action {action_index}.action", pages, modals)
                require(action.get("style", "secondary") in VALID_ACTION_STYLES, f"页面 {identifier} 的 action {action_index} style 无效")
                require(isinstance(action.get("disabled", False), bool), f"页面 {identifier} 的 action {action_index} disabled 必须为布尔值")
                params = action.get("params", {})
                require(isinstance(params, dict), f"页面 {identifier} 的 action {action_index}.params 必须是 object")
    for identifier, modal in modals.items():
        require_text(modal.get("title"), f"prototype.modals.{identifier}.title")
        require(modal.get("type", "dialog") in {"dialog", "drawer", "popover"}, f"弹层 {identifier} type 无效")
        appearance = modal.get("appearance", {})
        require(isinstance(appearance, dict), f"弹层 {identifier}.appearance 必须是 object")
        require(not (set(appearance) - {"dialog_size"}), f"弹层 {identifier}.appearance 存在未知字段")
        require(appearance.get("dialog_size", "medium") in VALID_DIALOG_SIZES, f"弹层 {identifier}.dialog_size 无效")
        page_id = modal.get("page_id")
        require(page_id in pages, f"弹层 {identifier} 引用了不存在的页面 {page_id}")
        fields = as_list(modal.get("fields", []), f"弹层 {identifier}.fields")
        field_names: set[str] = set()
        for field_index, field in enumerate(fields):
            require(isinstance(field, dict), f"弹层 {identifier} 的字段 {field_index} 必须是 object")
            name = require_id(field.get("name"), f"弹层 {identifier} 的字段 {field_index}.name")
            require(name not in field_names, f"弹层 {identifier} 的字段 name 重复: {name}")
            field_names.add(name)
            require_text(field.get("label"), f"弹层 {identifier} 的字段 {name}.label")
            require(field.get("type", "text") in VALID_FIELD_TYPES, f"弹层 {identifier} 的字段 {name}.type 无效")
            require(isinstance(field.get("required", False), bool), f"弹层 {identifier} 的字段 {name}.required 必须为布尔值")
            if field.get("type") == "select":
                require(bool(field.get("options")), f"弹层 {identifier} 的下拉字段 {name} 至少包含一个选项")
        submit = modal.get("submit", {})
        require(isinstance(submit, dict), f"弹层 {identifier}.submit 必须是 object")
        operation = submit.get("operation", "save")
        require(operation in VALID_SUBMIT_OPERATIONS, f"弹层 {identifier}.submit.operation 无效")
        if operation == "append":
            target_list = require_id(submit.get("target_list"), f"弹层 {identifier}.submit.target_list")
            require(target_list in list_ids, f"弹层 {identifier} 的提交目标列表不存在: {target_list}")
            record = submit.get("record")
            require(isinstance(record, dict) and bool(record), f"弹层 {identifier}.submit.record 必须是非空 object")
            require("id" in record, f"弹层 {identifier}.submit.record 必须定义 id")
            missing_record_fields = list_columns[target_list] - set(record)
            require(not missing_record_fields, f"弹层 {identifier}.submit.record 缺少列表字段: {', '.join(sorted(missing_record_fields))}")

    annotation_ids: set[str] = set()
    groups: dict[tuple[str, str, str], list[int]] = {}
    for _, annotation, page_id, path in iter_annotated_nodes(model):
        if annotation is None:
            continue
        require(isinstance(annotation, dict), f"{path}.annotation 必须是 object")
        annotation_id = require_id(annotation.get("id"), f"{path}.annotation.id")
        require(annotation_id not in annotation_ids, f"标注 id 重复: {annotation_id}")
        annotation_ids.add(annotation_id)
        order = annotation.get("order")
        require(isinstance(order, int) and not isinstance(order, bool) and order > 0, f"标注 {annotation_id}.order 必须是正整数")
        scope = annotation.get("scope") or {"type": "page", "id": page_id}
        require(isinstance(scope, dict) and scope.get("type") in VALID_SCOPES, f"标注 {annotation_id}.scope 无效")
        scope_id = require_text(scope.get("id"), f"标注 {annotation_id}.scope.id")
        for ref in annotation.get("rule_refs", []):
            require(ref in rules, f"标注 {annotation_id} 引用了不存在的规则 {ref}")
        for ref in annotation.get("acceptance_refs", []):
            require(ref in criteria, f"标注 {annotation_id} 引用了不存在的验收条件 {ref}")
        group_page = "*" if page_id == "*" else str(page_id)
        groups.setdefault((group_page, str(scope.get("type")), scope_id), []).append(order)

    for group, orders in groups.items():
        expected = list(range(1, len(orders) + 1))
        require(sorted(orders) == expected, f"标注分组 {group} 的 order 必须从 1 连续且不重复，实际为 {sorted(orders)}")

    return {
        "roles": roles,
        "modules": modules,
        "rules": rules,
        "criteria": criteria,
        "requirements": requirements,
        "pages": pages,
        "modals": modals,
    }


def dump_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
