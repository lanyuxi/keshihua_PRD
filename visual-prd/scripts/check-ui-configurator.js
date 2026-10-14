#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(__dirname, "ui-configurator-runtime.js"), "utf8");
const profile = JSON.parse(fs.readFileSync(path.join(root, "assets", "ui-profile-template.json"), "utf8"));
const context = { window: {} };
vm.createContext(context);
vm.runInContext(source, context, { filename: "ui-configurator-runtime.js" });

const runtime = context.window.VisualPRDUIConfigurator;
const checks = [];
function check(name, condition) {
  checks.push([name, Boolean(condition)]);
  if (!condition) throw new Error(name);
}

check("默认配置通过完整校验", runtime.validateProfile(profile).valid);

const invalidNumber = JSON.parse(JSON.stringify(profile));
invalidNumber.tokens.radii.control = -1;
check("越界数字被拒绝", !runtime.validateProfile(invalidNumber).valid);

const invalidContrast = JSON.parse(JSON.stringify(profile));
invalidContrast.tokens.colors.brand = "#FFFFFF";
invalidContrast.tokens.colors.brand_contrast = "#FFFFFF";
check("低对比度配色被拒绝", !runtime.validateProfile(invalidContrast).valid);

const invalidPageContrast = JSON.parse(JSON.stringify(profile));
invalidPageContrast.page_overrides = { detail: { tokens: { colors: { brand: "#FFFFFF" } } } };
check("页面覆盖的低对比度配色被拒绝", !runtime.validateProfile(invalidPageContrast).valid);

const legacy = JSON.parse(JSON.stringify(profile));
legacy.components.list.variant = "compact";
legacy.page_overrides = { detail: { components: { list: { variant: "compact" } } } };
const normalized = runtime.normalizeProfile(legacy);
check("旧版紧凑列表迁移为表格", normalized.components.list.variant === "table");
check("旧版紧凑列表迁移为紧凑密度", normalized.components.list.density === "compact");
check("页面覆盖同步迁移", normalized.page_overrides.detail.components.list.variant === "table" && normalized.page_overrides.detail.components.list.density === "compact");

console.log(`UI configurator checks: ${checks.length}/${checks.length} passed`);
checks.forEach(([name]) => console.log(`PASS ${name}`));
