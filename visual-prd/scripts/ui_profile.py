#!/usr/bin/env python3
"""Validation and deterministic CSS generation for Visual PRD UI profiles."""

from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
from typing import Any


DEFAULT_PROFILE: dict[str, Any] = {
    "schema_version": "1.0",
    "id": "neutral-review",
    "name": "中性评审样式",
    "tokens": {
        "colors": {
            "brand": "#5B55D6", "brand_contrast": "#FFFFFF", "ink": "#172033",
            "muted": "#667085", "line": "#DFE3EA", "surface": "#FFFFFF",
            "canvas": "#F3F5F9", "nav": "#181B2D", "nav_text": "#CFD3E7",
            "nav_active": "#2C3049", "success": "#16845B", "warning": "#B26A00",
            "danger": "#C03245", "focus": "#5B55D6", "backdrop": "rgba(15, 23, 42, 0.46)",
        },
        "typography": {"font_family": "system-ui, sans-serif", "base_size": 14, "line_height": 1.5},
        "radii": {"control": 9, "panel": 16, "overlay": 16},
        "spacing": {"page": 28, "panel": 22, "control_x": 13, "control_y": 9, "gap": 10},
        "shadows": {"panel": "none", "overlay": "strong"},
    },
    "components": {
        "filter": {"variant": "select"},
        "list": {"variant": "table", "density": "comfortable"},
        "tabs": {"variant": "underline"},
        "button": {"size": "medium"},
        "modal": {"dialog_size": "medium", "drawer_width": 480},
    },
    "page_overrides": {},
}

COLOR_KEYS = set(DEFAULT_PROFILE["tokens"]["colors"])
TOKEN_GROUPS = {"colors", "typography", "radii", "spacing", "shadows"}
COMPONENT_GROUPS = {"filter", "list", "tabs", "button", "modal"}
ENUMS = {
    ("components", "filter", "variant"): {"select", "segmented", "chips"},
    ("components", "list", "variant"): {"table", "compact", "cards"},
    ("components", "list", "density"): {"comfortable", "compact"},
    ("components", "tabs", "variant"): {"underline", "pills", "segmented"},
    ("components", "button", "size"): {"small", "medium", "large"},
    ("components", "modal", "dialog_size"): {"small", "medium", "large"},
    ("tokens", "shadows", "panel"): {"none", "soft", "medium", "strong"},
    ("tokens", "shadows", "overlay"): {"none", "soft", "medium", "strong"},
}
COLOR_RE = re.compile(r"^(?:#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}(?:\s*,\s*(?:0(?:\.\d+)?|1(?:\.0+)?))?\s*\))$")
FONT_RE = re.compile(r"^[A-Za-z0-9\u4e00-\u9fff ,\-'\"]+$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy aliases to one unambiguous component representation."""
    result = copy.deepcopy(profile)
    roots = [result, *(result.get("page_overrides") or {}).values()]
    for root in roots:
        list_settings = root.get("components", {}).get("list", {})
        if list_settings.get("variant") == "compact":
            list_settings["variant"] = "table"
            list_settings["density"] = "compact"
    return result


def _rgb(value: str) -> tuple[int, int, int] | None:
    value = value.strip()
    if value.startswith("#") and len(value) in (4, 7):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(character * 2 for character in digits)
        return tuple(int(digits[index:index + 2], 16) for index in (0, 2, 4))
    match = re.match(r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", value, re.I)
    if not match:
        return None
    channels = tuple(int(channel) for channel in match.groups())
    return channels if max(channels) <= 255 else None


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        channels = _rgb(value)
        if channels is None:
            return math.nan
        linear = []
        for value in channels:
            channel = value / 255
            linear.append(channel / 12.92 if channel <= .03928 else ((channel + .055) / 1.055) ** 2.4)
        return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]

    first, second = luminance(foreground), luminance(background)
    if math.isnan(first) or math.isnan(second):
        return 0
    return (max(first, second) + .05) / (min(first, second) + .05)


def validate_contrast(profile: dict[str, Any], label: str = "ui profile") -> None:
    colors = profile["tokens"]["colors"]
    pairs = (
        ("brand", "brand_contrast", "品牌色与品牌文字"),
        ("ink", "surface", "主文字与面板背景"),
        ("ink", "canvas", "主文字与页面背景"),
    )
    for foreground, background, name in pairs:
        require(contrast_ratio(colors[foreground], colors[background]) >= 4.5, f"{label} {name}对比度必须至少为 4.5:1")


ALLOWED_TOKEN_KEYS = {
    "colors": COLOR_KEYS,
    "typography": {"font_family", "base_size", "line_height"},
    "radii": {"control", "panel", "overlay"},
    "spacing": {"page", "panel", "control_x", "control_y", "gap"},
    "shadows": {"panel", "overlay"},
}
ALLOWED_COMPONENT_KEYS = {
    "filter": {"variant"}, "list": {"variant", "density"},
    "tabs": {"variant"}, "button": {"size"},
    "modal": {"dialog_size", "drawer_width"},
}


def validate_sections(tokens: Any, components: Any, prefix: str = "") -> None:
    token_label = f"{prefix}.tokens" if prefix else "ui profile tokens"
    component_label = f"{prefix}.components" if prefix else "ui profile components"
    require(isinstance(tokens, dict), f"{token_label} 必须是 object")
    require(isinstance(components, dict), f"{component_label} 必须是 object")
    require(not (set(tokens) - TOKEN_GROUPS), f"{token_label} 存在未知分组")
    require(not (set(components) - COMPONENT_GROUPS), f"{component_label} 存在未知分组")

    for group, fields in tokens.items():
        require(isinstance(fields, dict), f"{token_label}.{group} 必须是 object")
        require(not (set(fields) - ALLOWED_TOKEN_KEYS[group]), f"{token_label}.{group} 存在未知字段")
    for group, fields in components.items():
        require(isinstance(fields, dict), f"{component_label}.{group} 必须是 object")
        require(not (set(fields) - ALLOWED_COMPONENT_KEYS[group]), f"{component_label}.{group} 存在未知字段")

    for key, color in tokens.get("colors", {}).items():
        require(isinstance(color, str) and bool(COLOR_RE.fullmatch(color)), f"颜色 {token_label}.colors.{key} 无效")
    typography = tokens.get("typography", {})
    if "font_family" in typography:
        font = typography["font_family"]
        require(isinstance(font, str) and bool(FONT_RE.fullmatch(font)) and "url" not in font.lower(), "font_family 无效")
    if "base_size" in typography:
        require(isinstance(typography["base_size"], int) and 10 <= typography["base_size"] <= 24, "base_size 必须为 10–24")
    if "line_height" in typography:
        require(isinstance(typography["line_height"], (int, float)) and 1.2 <= typography["line_height"] <= 2.2, "line_height 必须为 1.2–2.2")
    for group in ("radii", "spacing"):
        for key, number in tokens.get(group, {}).items():
            require(isinstance(number, int) and 0 <= number <= 96, f"{token_label}.{group}.{key} 必须为 0–96 的整数")
    for path, choices in ENUMS.items():
        root, group, key = path
        section = tokens if root == "tokens" else components
        if key in section.get(group, {}):
            require(section[group][key] in choices, f"{prefix + '.' if prefix else ''}{root}.{group}.{key} 无效")
    modal = components.get("modal", {})
    if "drawer_width" in modal:
        require(isinstance(modal["drawer_width"], int) and 280 <= modal["drawer_width"] <= 960, "drawer_width 必须为 280–960")


def validate_profile(value: dict[str, Any]) -> dict[str, Any]:
    require(isinstance(value, dict), "界面规范根节点必须是 object")
    require(value.get("schema_version") == "1.0", "ui profile schema_version 必须为 1.0")
    require(isinstance(value.get("id"), str) and bool(IDENTIFIER_RE.fullmatch(value["id"])), "ui profile id 无效")
    require(isinstance(value.get("name"), str) and bool(value["name"].strip()), "ui profile name 不能为空")
    unknown = set(value) - {"schema_version", "id", "name", "tokens", "components", "page_overrides"}
    require(not unknown, f"ui profile 存在未知字段: {', '.join(sorted(unknown))}")

    tokens = value.get("tokens", {})
    components = value.get("components", {})
    validate_sections(tokens, components)
    page_overrides = value.get("page_overrides", {})
    require(isinstance(page_overrides, dict), "page_overrides 必须是 object")
    for page_id, override in page_overrides.items():
        require(isinstance(page_id, str) and bool(IDENTIFIER_RE.fullmatch(page_id)), f"page_overrides 页面 id 无效: {page_id}")
        require(isinstance(override, dict), f"page_overrides.{page_id} 必须是 object")
        require(not (set(override) - {"tokens", "components"}), f"page_overrides.{page_id} 存在未知字段")
        validate_sections(override.get("tokens", {}), override.get("components", {}), f"page_overrides.{page_id}")
    merged = normalize_profile(merge_dict(DEFAULT_PROFILE, value))
    validate_contrast(merged)
    for page_id in merged.get("page_overrides", {}):
        validate_contrast(effective_profile(merged, page_id), f"page_overrides.{page_id}")
    return merged


def load_ui_profile(path: Path | None) -> dict[str, Any]:
    if path is None:
        return copy.deepcopy(DEFAULT_PROFILE)
    value = json.loads(path.read_text(encoding="utf-8"))
    return validate_profile(value)


def effective_profile(profile: dict[str, Any], page_id: str | None) -> dict[str, Any]:
    """Resolve global UI defaults with an optional page-level visual override."""
    if not page_id:
        return copy.deepcopy(profile)
    override = (profile.get("page_overrides") or {}).get(page_id, {})
    return merge_dict(profile, override)


def shadow_value(level: str) -> str:
    return {
        "none": "none",
        "soft": "0 4px 18px rgba(23,32,51,.08)",
        "medium": "0 12px 36px rgba(23,32,51,.14)",
        "strong": "0 24px 80px rgba(23,32,51,.24)",
    }[level]


def profile_css(profile: dict[str, Any]) -> str:
    colors = profile["tokens"]["colors"]
    typography = profile["tokens"]["typography"]
    radii = profile["tokens"]["radii"]
    spacing = profile["tokens"]["spacing"]
    shadows = profile["tokens"]["shadows"]
    modal = profile["components"]["modal"]
    button_size = profile["components"]["button"]["size"]
    button_scale = {"small": (.78, .86), "medium": (1, 1), "large": (1.22, 1.14)}[button_size]
    return f"""
    :root {{
      color-scheme: light;
      --brand:{colors['brand']}; --brand-contrast:{colors['brand_contrast']};
      --ink:{colors['ink']}; --muted:{colors['muted']}; --line:{colors['line']};
      --surface:{colors['surface']}; --canvas:{colors['canvas']};
      --nav:{colors['nav']}; --nav-text:{colors['nav_text']}; --nav-active:{colors['nav_active']};
      --success:{colors['success']}; --warning:{colors['warning']}; --danger:{colors['danger']};
      --focus:{colors['focus']}; --backdrop:{colors['backdrop']};
      --font-family:{typography['font_family']}; --font-size:{typography['base_size']}px; --line-height:{typography['line_height']};
      --radius-control:{radii['control']}px; --radius-panel:{radii['panel']}px; --radius-overlay:{radii['overlay']}px;
      --space-page:{spacing['page']}px; --space-panel:{spacing['panel']}px;
      --control-x:{round(spacing['control_x'] * button_scale[0], 2)}px; --control-y:{round(spacing['control_y'] * button_scale[1], 2)}px;
      --gap:{spacing['gap']}px; --panel-shadow:{shadow_value(shadows['panel'])}; --overlay-shadow:{shadow_value(shadows['overlay'])};
      --drawer-width:{modal['drawer_width']}px;
    }}
    """.strip()
