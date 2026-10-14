#!/usr/bin/env python3
"""Compile a self-contained prototype source from declarative product-model pages."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

from model_core import load_model, validate_model
from ui_profile import effective_profile, load_ui_profile, profile_css


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def annotation_attr(node: dict) -> str:
    annotation = node.get("annotation")
    return f' data-anno="{esc(annotation["id"])}"' if isinstance(annotation, dict) else ""


def action_button(action: dict) -> str:
    label = esc(action.get("label", "操作"))
    command = esc(action.get("action", ""))
    style = esc(action.get("style", "secondary"))
    params = action.get("params") or {}
    params_attr = f" data-params='{esc(json.dumps(params, ensure_ascii=False, separators=(',', ':')))}'" if params else ""
    disabled = ' disabled aria-disabled="true"' if action.get("disabled") else ""
    return f'<button type="button" class="btn {style}" data-action="{command}"{params_attr}{annotation_attr(action)}{disabled}>{label}</button>'


def resolve_row_params(component: dict, row: dict) -> dict:
    templates = component.get("row_params") or {"id": "{id}"}

    def resolve(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return re.sub(r"\{([A-Za-z][A-Za-z0-9_-]*)\}", lambda match: str(row.get(match.group(1), "")), value)

    return {str(key): resolve(value) for key, value in templates.items()}


def render_component(component: dict, page_id: str, profile: dict) -> str:
    profile = effective_profile(profile, page_id)
    kind = component["type"]
    title = esc(component.get("title", ""))
    description = esc(component.get("description", component.get("text", "")))
    anno = annotation_attr(component)
    component_id = esc(component.get("id", f"{page_id}-{kind}"))
    appearance = component.get("appearance") or {}

    if kind == "hero":
        actions = "".join(action_button(item) for item in component.get("actions", []))
        return f'<section class="hero" id="{component_id}"{anno}><div><span class="eyebrow">{esc(component.get("eyebrow", "PRODUCT"))}</span><h1>{title}</h1><p>{description}</p></div><div class="hero-actions">{actions}</div></section>'
    if kind == "stats":
        items = "".join(f'<article class="stat"><span>{esc(item.get("label", ""))}</span><strong>{esc(item.get("value", "—"))}</strong></article>' for item in component.get("items", []))
        return f'<section class="stats" id="{component_id}"{anno}>{items}</section>'
    if kind == "text":
        return f'<section class="panel prose" id="{component_id}"{anno}><h2>{title}</h2><p>{description}</p></section>'
    if kind == "cards":
        cards = "".join(f'<article class="card"{annotation_attr(item)}><h3>{esc(item.get("title", ""))}</h3><p>{esc(item.get("description", ""))}</p></article>' for item in component.get("items", []))
        return f'<section class="panel" id="{component_id}"{anno}><h2>{title}</h2><div class="cards">{cards}</div></section>'
    if kind == "timeline":
        items = "".join(f'<li{annotation_attr(item)}><strong>{esc(item.get("title", ""))}</strong><span>{esc(item.get("description", ""))}</span></li>' for item in component.get("items", []))
        return f'<section class="panel" id="{component_id}"{anno}><h2>{title}</h2><ol class="timeline">{items}</ol></section>'
    if kind == "tabs":
        tab_variant = esc(appearance.get("variant", profile["components"]["tabs"]["variant"]))
        state_path = f"activeTabs.{page_id}"
        buttons = []
        panels = []
        for index, tab in enumerate(component.get("tabs", [])):
            tab_id = str(tab.get("id", f"tab-{index + 1}"))
            buttons.append(f'<button type="button" data-action="set-state:{state_path}={esc(tab_id)}" data-tab-button="{esc(page_id)}:{esc(tab_id)}"{annotation_attr(tab)}>{esc(tab.get("label", tab_id))}</button>')
            panels.append(f'<section class="tab-panel" data-tab-panel="{esc(page_id)}:{esc(tab_id)}"><h3>{esc(tab.get("title", tab.get("label", tab_id)))}</h3><p>{esc(tab.get("content", ""))}</p></section>')
        tab_lock = f' data-ui-variant-lock="{tab_variant}"' if "variant" in appearance else ""
        return f'<section class="panel" id="{component_id}"{anno}><div class="tabs tabs-{tab_variant}" data-ui-component="tabs"{tab_lock}>{"".join(buttons)}</div>{"".join(panels)}</section>'
    if kind == "table":
        list_id = str(component.get("list_id", component.get("id", f"{page_id}-list")))
        controls = component.get("controls") or {}
        filter_variant = appearance.get("filter_variant", profile["components"]["filter"]["variant"])
        list_variant = appearance.get("variant", profile["components"]["list"]["variant"])
        density = appearance.get("density", profile["components"]["list"]["density"])
        list_variant, density = normalize_list_variant(list_variant, density)
        control_html = ""
        if controls.get("search", True):
            control_html += f'<input class="search" type="search" placeholder="搜索" data-search="{esc(list_id)}" data-list-target="{esc(list_id)}">'
        for filter_spec in controls.get("filters", []):
            filter_key = esc(filter_spec.get("key", "status"))
            options = "".join(f'<option value="{esc(option.get("value", ""))}">{esc(option.get("label", option.get("value", "")))}</option>' for option in filter_spec.get("options", []))
            control_html += f'<select data-ui-filter-variant="select" data-filter="{filter_key}" data-list-target="{esc(list_id)}"{"" if filter_variant == "select" else " hidden"}><option value="all">全部</option>{options}</select>'
            for candidate in ("segmented", "chips"):
                buttons = [f'<button type="button" class="active" data-filter="{filter_key}=all" data-list-target="{esc(list_id)}" aria-pressed="true">全部</button>']
                buttons.extend(f'<button type="button" data-filter="{filter_key}={esc(option.get("value", ""))}" data-list-target="{esc(list_id)}" aria-pressed="false">{esc(option.get("label", option.get("value", "")))}</button>' for option in filter_spec.get("options", []))
                control_html += f'<div class="filter-group filter-{candidate}" data-ui-filter-variant="{candidate}"{"" if filter_variant == candidate else " hidden"}>{"".join(buttons)}</div>'
        columns = component.get("columns", [])
        header = "".join(f'<th><span role="button" tabindex="0" data-sort="{esc(column.get("key", ""))}" data-list-target="{esc(list_id)}">{esc(column.get("label", column.get("key", "")))}</span></th>' for column in columns)
        rows = []
        card_rows = []
        for row in component.get("rows", []):
            attrs = " ".join(f'data-{esc(key)}="{esc(value)}"' for key, value in row.items() if not isinstance(value, (dict, list)))
            cells = "".join(f'<td>{esc(row.get(column.get("key"), ""))}</td>' for column in columns)
            row_action = component.get("row_action")
            if row_action:
                command = str(row_action).replace("{id}", str(row.get("id", "")))
                params = json.dumps(resolve_row_params(component, row), ensure_ascii=False, separators=(",", ":"))
                action_label = esc(component.get("row_action_label", "查看详情"))
                cells += f'<td><button type="button" data-action="{esc(command)}" data-params=\'{esc(params)}\'>{action_label}</button></td>'
                card_action = f'<button type="button" data-action="{esc(command)}" data-params=\'{esc(params)}\'>{action_label}</button>'
            else:
                card_action = ""
            rows.append(f'<tr data-list-item data-search-text="{esc(" ".join(str(value) for value in row.values() if not isinstance(value, (dict, list))))}" {attrs}{annotation_attr(row)}>{cells}</tr>')
            card_fields = "".join(f'<div><span>{esc(column.get("label", column.get("key", "")))}</span><strong>{esc(row.get(column.get("key"), ""))}</strong></div>' for column in columns)
            card_rows.append(f'<article class="list-card" data-list-item data-search-text="{esc(" ".join(str(value) for value in row.values() if not isinstance(value, (dict, list))))}" {attrs}{annotation_attr(row)}>{card_fields}{card_action}</article>')
        action_header = "<th>操作</th>" if component.get("row_action") else ""
        if list_variant == "cards":
            list_markup = f'<div class="list-cards density-{esc(density)}" data-list="{esc(list_id)}" data-ui-list-view="cards">{"".join(card_rows)}</div><div class="empty-state" data-empty-for="{esc(list_id)}" hidden>暂无符合条件的数据</div>'
        else:
            compact = "compact" if list_variant == "compact" or density == "compact" else "comfortable"
            list_markup = f'<div class="table-wrap density-{compact}" data-ui-list-view="{esc(list_variant)}"><table><thead><tr>{header}{action_header}</tr></thead><tbody data-list="{esc(list_id)}">{"".join(rows)}</tbody></table></div><div class="empty-state" data-empty-for="{esc(list_id)}" hidden>暂无符合条件的数据</div>'
        return f'<section class="panel" id="{component_id}" data-ui-list-section data-ui-list-id="{esc(list_id)}"{anno}><div class="section-head"><div><h2>{title}</h2><p>{description}</p></div><div class="list-controls" data-list-controls="{esc(list_id)}">{control_html}</div></div>{list_markup}</section>'
    if kind == "custom":
        return f'<section id="{component_id}"{anno}>{component.get("html", "")}</section>'
    return ""


def render_modal(modal: dict, profile: dict) -> str:
    profile = effective_profile(profile, str(modal.get("page_id", "")))
    modal_id = str(modal["id"])
    form_id = f"{modal_id}-form"
    fields = []
    for field in modal.get("fields", []):
        name = str(field["name"])
        model = field.get("model", f"drafts.{modal_id}.{name}")
        field_type = field.get("type", "text")
        required = "required" if field.get("required") else ""
        validation = ' data-validate="required"' if field.get("required") else ""
        if field_type == "textarea":
            control = f'<textarea name="{esc(name)}" data-model="{esc(model)}"{validation}></textarea>'
        elif field_type == "select":
            options = "".join(f'<option value="{esc(option.get("value", ""))}">{esc(option.get("label", option.get("value", "")))}</option>' for option in field.get("options", []))
            control = f'<select name="{esc(name)}" data-model="{esc(model)}"{validation}>{options}</select>'
        else:
            control = f'<input type="{esc(field_type)}" name="{esc(name)}" data-model="{esc(model)}" {required}{validation}>'
        fields.append(f'<label{annotation_attr(field)}><span>{esc(field.get("label", name))}</span>{control}</label>')
    submit_label = esc((modal.get("submit") or {}).get("label", "确定"))
    submit = modal.get("submit") or {}
    submit_operation = esc(submit.get("operation", "save"))
    submit_target = f' data-submit-target="{esc(submit.get("target_list"))}"' if submit.get("target_list") else ""
    appearance = modal.get("appearance") or {}
    dialog_size = esc(appearance.get("dialog_size", profile["components"]["modal"]["dialog_size"]))
    dialog_lock = f' data-ui-dialog-lock="{dialog_size}"' if "dialog_size" in appearance else ""
    scope_id = str((modal.get("annotation") or {}).get("scope", {}).get("id", modal_id))
    modal_type = str(modal.get("type", "dialog"))
    annotation_scope = "drawer" if modal_type == "drawer" else "modal"
    return f'<section class="modal-card modal-{dialog_size}" data-modal="{esc(modal_id)}" data-modal-type="{esc(modal_type)}" data-ui-component="modal" data-ui-page-id="{esc(modal.get("page_id", ""))}"{dialog_lock} data-anno-scope="{annotation_scope}" data-anno-scope-id="{esc(scope_id)}" hidden{annotation_attr(modal)}><header><h2>{esc(modal["title"])}</h2><button type="button" data-action="close-modal" aria-label="关闭">×</button></header><form id="{esc(form_id)}" data-form="{esc(form_id)}" data-submit-operation="{submit_operation}"{submit_target}>{"".join(fields)}<div class="form-actions"><button type="button" data-action="close-modal">取消</button><button type="button" class="btn primary" data-action="submit:{esc(form_id)}">{submit_label}</button></div></form></section>'


def js_template(value: str) -> str:
    return value.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def normalize_list_variant(variant: str, density: str) -> tuple[str, str]:
    """Keep list structure and density independent while accepting the 4.1 legacy alias."""
    return ("table", "compact") if variant == "compact" else (variant, density)


def compile_prototype(model: dict, profile: dict | None = None) -> str:
    index = validate_model(model)
    profile = profile or load_ui_profile(None)
    prototype = model["prototype"]
    page_ids = list(index["pages"])
    first_page = page_ids[0]
    initial = dict(prototype.get("initial_state") or {})
    initial["currentPage"] = initial.get("currentPage", first_page)
    initial.setdefault("prototypeNotice", False)
    initial.setdefault("activeTabs", {})
    initial.setdefault("lists", {})
    initial.setdefault("drafts", {})
    list_schemas: dict[str, dict] = {}
    for page in prototype["pages"]:
        page_profile = effective_profile(profile, page["id"])
        for component in page.get("components", []):
            if component["type"] == "tabs" and component.get("tabs"):
                initial["activeTabs"].setdefault(page["id"], component["tabs"][0]["id"])
            if component["type"] == "table":
                list_id = str(component.get("list_id", component.get("id", f'{page["id"]}-list')))
                list_state = initial["lists"].setdefault(list_id, {"filters": {}, "search": "", "sort": {}})
                list_state.setdefault("filters", {})
                list_state.setdefault("search", "")
                list_state.setdefault("sort", {})
                list_state.setdefault("items", component.get("rows", []))
                appearance = component.get("appearance") or {}
                declared_variant = appearance.get("variant")
                declared_density = appearance.get("density")
                variant, density = normalize_list_variant(
                    declared_variant or page_profile["components"]["list"]["variant"],
                    declared_density or page_profile["components"]["list"]["density"],
                )
                if declared_variant == "compact":
                    declared_variant, declared_density = "table", "compact"
                list_schemas[list_id] = {
                    "variant": variant,
                    "density": density,
                    "declaredVariant": declared_variant,
                    "declaredDensity": declared_density,
                    "declaredFilterVariant": appearance.get("filter_variant"),
                    "hasFilters": bool((component.get("controls") or {}).get("filters")),
                    "pageId": page["id"],
                    "columns": component.get("columns", []),
                    "rowAction": component.get("row_action"),
                    "rowActionLabel": component.get("row_action_label", "查看详情"),
                    "rowParams": component.get("row_params") or {"id": "{id}"},
                }
    for modal in prototype.get("modals", []):
        initial["drafts"].setdefault(modal["id"], {field["name"]: "" for field in modal.get("fields", [])})

    nav_annotation = annotation_attr({"annotation": prototype.get("navigation_annotation")}) if prototype.get("navigation_annotation") else ""
    nav = "".join(f'<button type="button" data-action="navigate:{esc(page["id"])}" data-route-active="{esc(page["id"])}">{esc(page["title"])}</button>' for page in prototype["pages"])
    page_entries = []
    for page in prototype["pages"]:
        content = "".join(render_component(component, page["id"], profile) for component in page.get("components", []))
        markup = f'<main class="page" data-page="{esc(page["id"])}" data-page-label="{esc(page["title"])}"{annotation_attr(page)} hidden><div class="route-context" data-route-context hidden></div>{content}</main>'
        page_entries.append(f'{json.dumps(page["id"], ensure_ascii=False)}: {{ render: () => `{js_template(markup)}` }}')

    modal_entries = []
    action_entries = []
    submit_specs: dict[str, dict] = {}
    for modal in prototype.get("modals", []):
        modal_markup = render_modal(modal, profile)
        modal_entries.append(f'{json.dumps(modal["id"], ensure_ascii=False)}: {{ render: () => `{js_template(modal_markup)}` }}')
        form_id = f'{modal["id"]}-form'
        submit_specs[modal["id"]] = modal.get("submit") or {"operation": "save"}
        action_entries.append(
            f'{json.dumps("submit:" + form_id)}: ({{ values, state }}) => '
            f'handleGeneratedSubmit({json.dumps(modal["id"], ensure_ascii=False)}, values, state)'
        )

    source = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    {profile_css(profile)}
    * {{ box-sizing:border-box; }} [hidden] {{ display:none!important; }} body {{ margin:0; color:var(--ink); background:var(--canvas); font:var(--font-size)/var(--line-height) var(--font-family); }} button,input,select,textarea {{ font:inherit; }} button {{ cursor:pointer; }} button:disabled,[aria-disabled="true"] {{ cursor:not-allowed; opacity:.45; }} button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible {{ outline:3px solid color-mix(in srgb,var(--focus) 30%,transparent); outline-offset:2px; }}
    .shell {{ min-height:100vh; display:grid; grid-template-columns:220px 1fr; }} .nav {{ padding:24px 16px; color:var(--brand-contrast); background:var(--nav); }} .brand {{ margin:0 0 24px; font-size:18px; }} .nav button {{ width:100%; margin:4px 0; padding:11px 12px; border:0; border-radius:var(--radius-control); color:var(--nav-text); background:transparent; text-align:left; }} .nav button.active {{ color:var(--brand-contrast); background:var(--nav-active); }}
    .content {{ padding:var(--space-page); overflow:auto; }} .page {{ max-width:1180px; margin:auto; }} .route-context {{ margin:0 0 12px; padding:8px 12px; border:1px solid var(--line); border-radius:var(--radius-control); color:var(--muted); background:var(--surface); }} .hero,.panel {{ margin-bottom:18px; padding:var(--space-panel); border:1px solid var(--line); border-radius:var(--radius-panel); background:var(--surface); box-shadow:var(--panel-shadow); }} .hero {{ display:flex; align-items:center; justify-content:space-between; gap:24px; background:var(--brand); color:var(--brand-contrast); }} .hero h1 {{ margin:4px 0; font-size:30px; }} .hero p {{ margin:0; opacity:.86; }} .eyebrow {{ font-size:12px; font-weight:700; letter-spacing:.12em; }} .hero-actions,.form-actions,.section-head,.list-controls {{ display:flex; align-items:center; gap:var(--gap); }} .section-head {{ justify-content:space-between; }}
    .btn,button {{ padding:var(--control-y) var(--control-x); border:1px solid var(--line); border-radius:var(--radius-control); background:var(--surface); color:var(--ink); }} .hero .btn {{ border-color:transparent; }} .btn.primary {{ color:var(--brand-contrast); background:var(--brand); border-color:var(--brand); }} .btn.ghost {{ border-color:transparent; background:transparent; }} .btn.danger {{ color:var(--danger); border-color:var(--danger); }} .stats,.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:18px; }} .stat,.card {{ padding:18px; border:1px solid var(--line); border-radius:var(--radius-panel); background:var(--surface); }} .stat span,.list-card span {{ color:var(--muted); }} .stat strong {{ display:block; margin-top:6px; font-size:26px; }}
    h2 {{ margin:0 0 12px; }} p {{ white-space:pre-line; }} .table-wrap {{ overflow:auto; }} table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:12px; border-bottom:1px solid var(--line); text-align:left; }} .density-compact th,.density-compact td {{ padding:8px 10px; }} th {{ color:var(--muted); background:color-mix(in srgb,var(--canvas) 78%,var(--surface)); }} .search,select,input,textarea {{ padding:var(--control-y) var(--control-x); border:1px solid var(--line); border-radius:var(--radius-control); background:var(--surface); color:var(--ink); }} [aria-invalid="true"] {{ border-color:var(--danger)!important; }} .filter-group {{ display:flex; align-items:center; gap:4px; }} .filter-segmented {{ padding:4px; border:1px solid var(--line); border-radius:var(--radius-control); }} .filter-chips button {{ border-radius:999px; }} .filter-group button.active {{ color:var(--brand-contrast); border-color:var(--brand); background:var(--brand); }}
    .tabs {{ display:flex; gap:8px; border-bottom:1px solid var(--line); }} .tabs button.active {{ color:var(--brand); border-color:var(--brand); }} .tabs-pills,.tabs-segmented {{ display:inline-flex; padding:4px; border:1px solid var(--line); border-radius:var(--radius-control); }} .tabs-pills {{ border-color:transparent; }} .tabs-pills button {{ border-radius:999px; }} .tabs-pills button.active,.tabs-segmented button.active {{ color:var(--brand-contrast); background:var(--brand); }} .tab-panel {{ padding:18px 4px 2px; }} .timeline li {{ margin:12px 0; }} .timeline span {{ display:block; color:var(--muted); }}
    .list-cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:var(--gap); }} .list-card {{ display:grid; gap:10px; padding:16px; border:1px solid var(--line); border-radius:var(--radius-panel); background:var(--surface); }} .list-card div {{ display:flex; justify-content:space-between; gap:12px; }} .density-compact.list-cards .list-card {{ padding:11px; gap:6px; }} .empty-state {{ padding:24px; color:var(--muted); text-align:center; border:1px dashed var(--line); border-radius:var(--radius-panel); }}
    .modal-card {{ width:min(520px,calc(100vw - 32px)); padding:var(--space-panel); border-radius:var(--radius-overlay); background:var(--surface); box-shadow:var(--overlay-shadow); }} .modal-small {{ width:min(380px,calc(100vw - 32px)); }} .modal-large {{ width:min(720px,calc(100vw - 32px)); }} .modal-card[data-modal-type="drawer"] {{ width:min(var(--drawer-width),calc(100vw - 24px)); }} .modal-card header {{ display:flex; align-items:center; justify-content:space-between; }} .modal-card form {{ display:grid; gap:14px; }} .modal-card label span {{ display:block; margin-bottom:5px; }} .modal-card input,.modal-card select,.modal-card textarea {{ width:100%; }} .form-actions {{ justify-content:flex-end; }} #toast-root {{ position:fixed; right:24px; bottom:24px; padding:10px 16px; border-radius:var(--radius-control); color:var(--brand-contrast); background:var(--ink); opacity:0; transform:translateY(8px); transition:.2s; }} #toast-root.show {{ opacity:1; transform:none; }}
    @media(max-width:720px) {{ .shell {{ grid-template-columns:1fr; }} .nav {{ display:flex; align-items:center; gap:8px; padding:12px; overflow:auto; }} .brand {{ margin:0 10px 0 0; white-space:nowrap; }} .nav button {{ width:auto; white-space:nowrap; }} .content {{ padding:14px; }} .hero,.section-head {{ align-items:flex-start; flex-direction:column; }} }}
  </style>
</head>
<body data-anno-page="{esc(first_page)}">
  <div class="shell"><nav class="nav"{nav_annotation}><h1 class="brand">{esc(model['product']['name'])}</h1>{nav}</nav><div class="content" id="app"></div></div>
  <div id="modal-root"></div><div id="toast-root" role="status"></div>
  <script>
    const initialState = {json.dumps(initial, ensure_ascii=False, indent=2)};
    const pages = {{{', '.join(page_entries)}}};
    const modals = {{{', '.join(modal_entries)}}};
    const listSchemas = {json.dumps(list_schemas, ensure_ascii=False)};
    const initialUiProfile = {json.dumps(profile, ensure_ascii=False)};
    const submitSpecs = {json.dumps(submit_specs, ensure_ascii=False)};
    const generatedText = value => value == null ? '' : String(value);
    const generatedTemplate = (value, source) => typeof value === 'string'
      ? value.replace(/\{{([A-Za-z][A-Za-z0-9_-]*)\}}/g, (_, key) => generatedText(source[key]))
      : value;
    const generatedParams = (templates, row) => Object.fromEntries(
      Object.entries(templates || {{ id: '{{id}}' }}).map(([key, value]) => [key, generatedTemplate(value, row)])
    );
    const uiClone = value => JSON.parse(JSON.stringify(value));
    const uiMerge = (base, patch) => {{
      const result = uiClone(base || {{}});
      Object.entries(patch || {{}}).forEach(([key, value]) => {{
        result[key] = value && typeof value === 'object' && !Array.isArray(value) && result[key] && typeof result[key] === 'object'
          ? uiMerge(result[key], value)
          : uiClone(value);
      }});
      return result;
    }};
    const effectiveUiProfile = (profile, pageId) => uiMerge(profile, profile.page_overrides?.[pageId] || {{}});
    const uiShadow = level => ({{ none:'none', soft:'0 4px 18px rgba(23,32,51,.08)', medium:'0 12px 36px rgba(23,32,51,.14)', strong:'0 24px 80px rgba(23,32,51,.24)' }}[level] || 'none');
    function applyUiTokens(effective) {{
      const root = document.documentElement.style;
      const colors = effective.tokens.colors;
      Object.entries(colors).forEach(([key, value]) => root.setProperty(`--${{key.replaceAll('_', '-')}}`, value));
      const type = effective.tokens.typography;
      root.setProperty('--font-family', type.font_family); root.setProperty('--font-size', `${{type.base_size}}px`); root.setProperty('--line-height', type.line_height);
      const radii = effective.tokens.radii;
      root.setProperty('--radius-control', `${{radii.control}}px`); root.setProperty('--radius-panel', `${{radii.panel}}px`); root.setProperty('--radius-overlay', `${{radii.overlay}}px`);
      const spacing = effective.tokens.spacing;
      const scale = ({{ small:[.78,.86], medium:[1,1], large:[1.22,1.14] }})[effective.components.button.size] || [1,1];
      root.setProperty('--space-page', `${{spacing.page}}px`); root.setProperty('--space-panel', `${{spacing.panel}}px`); root.setProperty('--gap', `${{spacing.gap}}px`);
      root.setProperty('--control-x', `${{Math.round(spacing.control_x * scale[0] * 100) / 100}}px`); root.setProperty('--control-y', `${{Math.round(spacing.control_y * scale[1] * 100) / 100}}px`);
      root.setProperty('--panel-shadow', uiShadow(effective.tokens.shadows.panel)); root.setProperty('--overlay-shadow', uiShadow(effective.tokens.shadows.overlay));
      root.setProperty('--drawer-width', `${{effective.components.modal.drawer_width}}px`);
    }}
    function buildListView(listId, variant, density) {{
      const schema = listSchemas[listId];
      const section = [...document.querySelectorAll('[data-ui-list-section]')].find(node => node.dataset.uiListId === listId);
      const current = section?.querySelector('[data-ui-list-view]');
      if (!schema || !section || !current) return;
      if (variant === 'compact') {{ variant = 'table'; density = 'compact'; }}
      const currentVariant = current.dataset.uiListView;
      const densityClass = density === 'compact' ? 'compact' : 'comfortable';
      if (currentVariant === variant) {{
        current.classList.remove('density-compact', 'density-comfortable'); current.classList.add(`density-${{densityClass}}`);
        schema.density = density; return;
      }}
      let replacement;
      if (variant === 'cards') {{
        replacement = document.createElement('div'); replacement.className = `list-cards density-${{densityClass}}`; replacement.dataset.list = listId;
      }} else {{
        replacement = document.createElement('div'); replacement.className = `table-wrap density-${{densityClass}}`;
        const table = document.createElement('table'); const thead = document.createElement('thead'); const headRow = document.createElement('tr');
        schema.columns.forEach(column => {{ const th = document.createElement('th'); const sort = document.createElement('span'); sort.role = 'button'; sort.tabIndex = 0; sort.dataset.sort = column.key; sort.dataset.listTarget = listId; sort.textContent = column.label || column.key; th.appendChild(sort); headRow.appendChild(th); }});
        if (schema.rowAction) {{ const th = document.createElement('th'); th.textContent = '操作'; headRow.appendChild(th); }}
        const body = document.createElement('tbody'); body.dataset.list = listId; thead.appendChild(headRow); table.append(thead, body); replacement.appendChild(table);
      }}
      replacement.dataset.uiListView = variant;
      schema.variant = variant; schema.density = density;
      current.replaceWith(replacement);
    }}
    function applyUiComponents(profile) {{
      Object.entries(listSchemas).forEach(([listId, schema]) => {{
        const effective = effectiveUiProfile(profile, schema.pageId);
        const settings = effective.components;
        const filterVariant = schema.declaredFilterVariant || settings.filter.variant;
        const listVariant = schema.declaredVariant || settings.list.variant;
        const listDensity = schema.declaredDensity || settings.list.density;
        const section = [...document.querySelectorAll('[data-ui-list-section]')].find(node => node.dataset.uiListId === listId);
        section?.querySelectorAll('[data-ui-filter-variant]').forEach(control => {{
          control.hidden = control.dataset.uiFilterVariant !== filterVariant;
          if (control.matches('select[data-filter]')) control.value = window.__proto?.state?.lists?.[listId]?.filters?.[control.dataset.filter] || 'all';
        }});
        buildListView(listId, listVariant, listDensity);
      }});
      document.querySelectorAll('[data-page]').forEach(page => {{
        const settings = effectiveUiProfile(profile, page.dataset.page).components;
        page.querySelectorAll('[data-ui-component="tabs"]').forEach(tabs => {{ const variant = tabs.dataset.uiVariantLock || settings.tabs.variant; tabs.classList.remove('tabs-underline','tabs-pills','tabs-segmented'); tabs.classList.add(`tabs-${{variant}}`); }});
      }});
      document.querySelectorAll('[data-ui-component="modal"]').forEach(modal => {{
        const settings = effectiveUiProfile(profile, modal.dataset.uiPageId).components;
        const size = modal.dataset.uiDialogLock || settings.modal.dialog_size;
        modal.classList.remove('modal-small','modal-medium','modal-large'); modal.classList.add(`modal-${{size}}`);
      }});
      window.__proto?.render();
    }}
    function applyUiProfile(profile, pageId) {{
      const activePage = pageId || window.__proto?.state?.route?.pageId || initialState.currentPage;
      applyUiTokens(effectiveUiProfile(profile, activePage));
      applyUiComponents(profile);
      requestAnimationFrame(() => window.AnnotationRuntime?.refresh());
    }}
    function describeUiProfile(pageId) {{
      const result = {{}};
      const describe = (path, nodes, locked) => {{
        const total = nodes.length;
        const lockedCount = nodes.filter(locked).length;
        result[path] = {{ total, lockedCount, partial: lockedCount > 0 && lockedCount < total }};
      }};
      const lists = Object.values(listSchemas).filter(schema => schema.pageId === pageId);
      describe('components.filter.variant', lists.filter(schema => schema.hasFilters), schema => Boolean(schema.declaredFilterVariant));
      describe('components.list.variant', lists, schema => Boolean(schema.declaredVariant));
      describe('components.list.density', lists, schema => Boolean(schema.declaredDensity));
      const page = document.querySelector(`[data-page="${{CSS.escape(pageId)}}"]`);
      describe('components.tabs.variant', [...(page?.querySelectorAll('[data-ui-component="tabs"]') || [])], node => Boolean(node.dataset.uiVariantLock));
      const modals = [...document.querySelectorAll(`[data-ui-component="modal"][data-ui-page-id="${{CSS.escape(pageId)}}"]`)];
      describe('components.modal.dialog_size', modals, node => Boolean(node.dataset.uiDialogLock));
      return result;
    }}
    const generatedRecord = (template, values) => Object.fromEntries(Object.entries(template || {{}}).map(([key, value]) => {{
      if (value === '$auto') return [key, `item-${{Date.now()}}-${{Math.random().toString(36).slice(2, 7)}}`];
      return [key, generatedTemplate(value, values)];
    }}));
    function generatedActionButton(schema, row) {{
      if (!schema.rowAction) return null;
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.action = generatedTemplate(schema.rowAction, row);
      button.dataset.params = JSON.stringify(generatedParams(schema.rowParams, row));
      button.textContent = schema.rowActionLabel || '查看详情';
      return button;
    }}
    function renderGeneratedList(list, items) {{
      const schema = listSchemas[list.dataset.list];
      if (!schema) return;
      const nodes = (items || []).map(row => {{
        const item = document.createElement(schema.variant === 'cards' ? 'article' : 'tr');
        if (schema.variant === 'cards') item.className = 'list-card';
        item.dataset.listItem = '';
        item.dataset.searchText = Object.values(row).filter(value => !value || typeof value !== 'object').map(generatedText).join(' ');
        Object.entries(row).forEach(([key, value]) => {{ if (value == null || typeof value === 'object') return; item.setAttribute(`data-${{key}}`, generatedText(value)); }});
        if (row.annotation?.id) item.dataset.anno = row.annotation.id;
        schema.columns.forEach(column => {{
          const cell = document.createElement(schema.variant === 'cards' ? 'div' : 'td');
          if (schema.variant === 'cards') {{ const label = document.createElement('span'); label.textContent = column.label || column.key; const value = document.createElement('strong'); value.textContent = generatedText(row[column.key]); cell.append(label, value); }}
          else cell.textContent = generatedText(row[column.key]);
          item.appendChild(cell);
        }});
        const action = generatedActionButton(schema, row);
        if (action) {{ if (schema.variant === 'cards') item.appendChild(action); else {{ const cell = document.createElement('td'); cell.appendChild(action); item.appendChild(cell); }} }}
        return item;
      }});
      list.replaceChildren(...nodes);
    }}
    const listRenderers = Object.fromEntries(Object.keys(listSchemas).map(listId => [listId, (list, items) => renderGeneratedList(list, items)]));
    function handleGeneratedSubmit(modalId, values, state) {{
      const spec = submitSpecs[modalId] || {{ operation: 'save' }};
      const currentDraft = state.drafts?.[modalId] || {{}};
      const patch = {{ drafts: {{ [modalId]: spec.operation === 'append' ? Object.fromEntries(Object.keys(currentDraft).map(key => [key, ''])) : {{ ...values }} }} }};
      if (spec.operation === 'append') {{
        const target = spec.target_list;
        const currentList = state.lists?.[target] || {{ items: [] }};
        patch.lists = {{ [target]: {{ items: [...(currentList.items || []), generatedRecord(spec.record, values)] }} }};
      }}
      window.__proto.closeModal();
      const root = document.querySelector('#toast-root');
      root.textContent = spec.success_message || (spec.operation === 'append' ? '已创建' : '已保存');
      root.classList.add('show'); setTimeout(() => root.classList.remove('show'), 1800);
      return patch;
    }}
    const actions = {{{', '.join(action_entries)}}};
    document.querySelector('#app').innerHTML = Object.values(pages).map(page => page.render(initialState)).join('');
    document.querySelector('#modal-root').innerHTML = Object.values(modals).map(modal => modal.render(initialState)).join('');
  </script>
  <script src="prototype-runtime.js"></script>
  <script>
    const submitHandlers = Object.fromEntries(Object.entries(actions).filter(([name]) => name.startsWith('submit:')).map(([name, handler]) => [name.slice(7), handler]));
    window.__proto.init({{
      initialState: {{ ...initialState, route: {{ pageId: initialState.currentPage, params: {{}} }} }},
      submitHandlers,
      listRenderers,
      render: (state) => {{
        document.body.dataset.annoPage = state.route.pageId;
        document.querySelectorAll('[data-route-context]').forEach(region => {{
          const active = region.closest('[data-page]')?.dataset.page === state.route.pageId;
          const entries = active ? Object.entries(state.route.params || {{}}) : [];
          region.hidden = !entries.length;
          region.textContent = entries.length ? `当前记录：${{entries.map(([key, value]) => `${{key}}=${{value}}`).join(' · ')}}` : '';
        }});
        document.querySelectorAll('[data-tab-button]').forEach(button => {{ const [page, tab] = button.dataset.tabButton.split(':'); button.classList.toggle('active', state.activeTabs?.[page] === tab); }});
        document.querySelectorAll('[data-tab-panel]').forEach(panel => {{ const [page, tab] = panel.dataset.tabPanel.split(':'); panel.hidden = state.activeTabs?.[page] !== tab; }});
        requestAnimationFrame(() => window.AnnotationRuntime?.refresh());
      }}
    }});
    window.__vprdUiProfile = {{
      apply: (nextProfile, pageId) => applyUiProfile(uiClone(nextProfile), pageId),
      describe: pageId => describeUiProfile(pageId),
      getInitial: () => uiClone(initialUiProfile)
    }};
    applyUiProfile(initialUiProfile, initialState.currentPage);
  </script>
  <script>/*__ANNOTATION_RUNTIME__*/</script>
  <script>
    const ANNOTATIONS = __ANNOTATION_DATA__;
    window.AnnotationRuntime.init({{ annotations: ANNOTATIONS, pageId: () => window.__proto.state.route.pageId }});
  </script>
</body>
</html>
'''
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description="从产品模型生成原型 HTML 源文件")
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--ui-profile", type=Path, help="可选界面规范 JSON")
    args = parser.parse_args()
    try:
        source = compile_prototype(load_model(args.model), load_ui_profile(args.ui_profile))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(source, encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"PASS: 已生成 {args.output}")


if __name__ == "__main__":
    main()
