#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");

function usage() {
  console.error("用法: node check-interactions.js <prototype.html>");
}

function lineNumber(source, index) {
  return source.slice(0, index).split("\n").length;
}

function skipSpaceAndComments(source, start) {
  let index = start;
  while (index < source.length) {
    if (/\s/.test(source[index])) {
      index += 1;
      continue;
    }
    if (source.startsWith("//", index)) {
      const end = source.indexOf("\n", index + 2);
      return end < 0 ? source.length : skipSpaceAndComments(source, end + 1);
    }
    if (source.startsWith("/*", index)) {
      const end = source.indexOf("*/", index + 2);
      return end < 0 ? source.length : skipSpaceAndComments(source, end + 2);
    }
    break;
  }
  return index;
}

function readQuoted(source, start) {
  const quote = source[start];
  let value = "";
  let index = start + 1;
  while (index < source.length) {
    const character = source[index];
    if (character === "\\") {
      if (index + 1 < source.length) value += source[index + 1];
      index += 2;
      continue;
    }
    if (character === quote) return { value, end: index + 1 };
    value += character;
    index += 1;
  }
  return { value, end: source.length };
}

function skipTemplate(source, start) {
  let index = start + 1;
  while (index < source.length) {
    if (source[index] === "\\") {
      index += 2;
      continue;
    }
    if (source[index] === "`") return index + 1;
    index += 1;
  }
  return source.length;
}

function findMatchingBrace(source, start) {
  let depth = 0;
  let index = start;
  while (index < source.length) {
    const character = source[index];
    if (character === "\"" || character === "'") {
      index = readQuoted(source, index).end;
      continue;
    }
    if (character === "`") {
      index = skipTemplate(source, index);
      continue;
    }
    if (source.startsWith("//", index)) {
      const end = source.indexOf("\n", index + 2);
      index = end < 0 ? source.length : end + 1;
      continue;
    }
    if (source.startsWith("/*", index)) {
      const end = source.indexOf("*/", index + 2);
      index = end < 0 ? source.length : end + 2;
      continue;
    }
    if (character === "{") depth += 1;
    if (character === "}") {
      depth -= 1;
      if (depth === 0) return index;
    }
    index += 1;
  }
  return -1;
}

function skipValue(source, start, objectEnd) {
  let index = start;
  let braces = 0;
  let brackets = 0;
  let parentheses = 0;
  while (index < objectEnd) {
    const character = source[index];
    if (character === "\"" || character === "'") {
      index = readQuoted(source, index).end;
      continue;
    }
    if (character === "`") {
      index = skipTemplate(source, index);
      continue;
    }
    if (source.startsWith("//", index) || source.startsWith("/*", index)) {
      index = skipSpaceAndComments(source, index);
      continue;
    }
    if (character === "{") braces += 1;
    else if (character === "}") {
      if (braces === 0 && brackets === 0 && parentheses === 0) return index;
      braces -= 1;
    } else if (character === "[") brackets += 1;
    else if (character === "]") brackets -= 1;
    else if (character === "(") parentheses += 1;
    else if (character === ")") parentheses -= 1;
    else if (character === "," && braces === 0 && brackets === 0 && parentheses === 0) return index;
    index += 1;
  }
  return index;
}

function readPropertyKey(source, start) {
  const index = skipSpaceAndComments(source, start);
  if (source[index] === "\"" || source[index] === "'") {
    const quoted = readQuoted(source, index);
    return { key: quoted.value, end: quoted.end };
  }
  const match = source.slice(index).match(/^([A-Za-z_$][\w$-]*|\d+(?:\.\d+)?)/);
  if (!match) return null;
  return { key: match[1], end: index + match[0].length };
}

function collectObjectPaths(source, objectStart, prefix = "", paths = new Set()) {
  const objectEnd = findMatchingBrace(source, objectStart);
  if (objectEnd < 0) return { end: source.length, paths };

  let index = objectStart + 1;
  while (index < objectEnd) {
    index = skipSpaceAndComments(source, index);
    while (source[index] === ",") index = skipSpaceAndComments(source, index + 1);
    if (index >= objectEnd) break;

    if (source.startsWith("...", index)) {
      index = skipValue(source, index + 3, objectEnd);
      continue;
    }

    const property = readPropertyKey(source, index);
    if (!property) {
      index += 1;
      continue;
    }
    index = skipSpaceAndComments(source, property.end);
    if (source[index] !== ":") {
      index = skipValue(source, index, objectEnd);
      continue;
    }

    const fullPath = prefix ? `${prefix}.${property.key}` : property.key;
    paths.add(fullPath);
    index = skipSpaceAndComments(source, index + 1);
    if (source[index] === "{") {
      const nested = collectObjectPaths(source, index, fullPath, paths);
      index = nested.end + 1;
    } else {
      index = skipValue(source, index, objectEnd);
    }
  }
  return { end: objectEnd, paths };
}

function collectTopLevelEntries(source, objectStart) {
  const objectEnd = findMatchingBrace(source, objectStart);
  const entries = new Map();
  if (objectEnd < 0) return entries;
  let index = objectStart + 1;
  while (index < objectEnd) {
    index = skipSpaceAndComments(source, index);
    while (source[index] === ",") index = skipSpaceAndComments(source, index + 1);
    if (index >= objectEnd) break;
    if (source.startsWith("...", index)) {
      index = skipValue(source, index + 3, objectEnd);
      continue;
    }
    const property = readPropertyKey(source, index);
    if (!property) { index += 1; continue; }
    index = skipSpaceAndComments(source, property.end);
    if (source[index] !== ":") {
      index = skipValue(source, index, objectEnd);
      continue;
    }
    const valueStart = skipSpaceAndComments(source, index + 1);
    const valueEnd = skipValue(source, valueStart, objectEnd);
    entries.set(property.key, source.slice(valueStart, valueEnd).trim());
    index = valueEnd;
  }
  return entries;
}

function extractObject(source, name) {
  const declaration = new RegExp(`\\b(?:const|let|var)\\s+${name}\\s*=\\s*\\{`, "m").exec(source);
  if (!declaration) return { found: false, paths: new Set(), keys: new Set(), entries: new Map() };
  const objectStart = declaration.index + declaration[0].lastIndexOf("{");
  const { paths } = collectObjectPaths(source, objectStart);
  const keys = new Set([...paths].filter(item => !item.includes(".")));
  return { found: true, paths, keys, entries: collectTopLevelEntries(source, objectStart) };
}

function parseAttributes(tagSource) {
  const attributes = new Map();
  const expression = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
  let match;
  while ((match = expression.exec(tagSource))) {
    const name = match[1].toLowerCase();
    if (name.startsWith("<")) continue;
    attributes.set(name, match[2] ?? match[3] ?? match[4] ?? "");
  }
  return attributes;
}

function decodeHtml(value) {
  return String(value || "")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

function extractInteractionPoints(source) {
  const points = [];
  const tagPattern = /<([A-Za-z][\w:-]*)\b[^>]*>/g;
  let match;
  while ((match = tagPattern.exec(source))) {
    const tag = match[1].toLowerCase();
    if (tag === "script" || tag === "style") continue;
    const attributes = parseAttributes(match[0]);
    const action = attributes.get("data-action");
    const runtimeBinding = ["data-filter", "data-sort", "data-search", "data-model"]
      .find(name => attributes.has(name));
    const isNativeInteractive = tag === "button" || tag === "a";
    if (action === undefined && !runtimeBinding && !isNativeInteractive) continue;
    points.push({
      action,
      runtimeBinding,
      bindingValue: runtimeBinding ? attributes.get(runtimeBinding) : undefined,
      params: attributes.get("data-params"),
      tag,
      href: attributes.has("href") ? attributes.get("href") : undefined,
      line: lineNumber(source, match.index),
      source: match[0].replace(/\s+/g, " ").slice(0, 160)
    });
  }
  return points;
}

function stateHasPath(statePaths, requestedPath) {
  const normalized = requestedPath.trim();
  return statePaths.has(normalized) || [...statePaths].some(path => path.startsWith(`${normalized}.`));
}

function formExists(source, formId) {
  const escaped = formId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`<form\\b[^>]*(?:id|data-form)\\s*=\\s*["']${escaped}["']`, "i");
  return pattern.test(source);
}

function isCallableExpression(source) {
  const value = String(source || "").trim();
  return /^(?:async\s+)?function\b/.test(value) || value.includes("=>");
}

function checkAction(point, context) {
  const action = (point.action || "").trim();
  if (!action) return "data-action 为空";
  const separator = action.indexOf(":");
  const type = separator < 0 ? action : action.slice(0, separator);
  const payload = separator < 0 ? "" : action.slice(separator + 1);

  const declaredHandler = context.actionEntries.get(action);
  if (declaredHandler !== undefined && !isCallableExpression(declaredHandler)) {
    return `actions 中的处理器 “${action}” 不是函数`;
  }
  if (type === "navigate") {
    if (!payload) return "navigate 缺少目标页面";
    if (!context.pageKeys.has(payload)) return `pages 中不存在页面 “${payload}”`;
    if (point.params !== undefined) {
      try {
        const value = JSON.parse(decodeHtml(point.params));
        if (!value || Array.isArray(value) || typeof value !== "object") return "data-params 必须是 JSON object";
      } catch (_) {
        return "data-params 不是有效 JSON";
      }
    }
    return null;
  }
  if (type === "open-modal") {
    if (!payload) return "open-modal 缺少目标弹层";
    return context.modalKeys.has(payload) ? null : `modals 中不存在弹层 “${payload}”`;
  }
  if (type === "set-state") {
    const equals = payload.indexOf("=");
    const key = (equals < 0 ? payload : payload.slice(0, equals)).trim();
    if (!key) return "set-state 缺少状态 key";
    return stateHasPath(context.statePaths, key) ? null : `initialState 中不存在状态 “${key}”`;
  }
  if (type === "toggle") {
    if (!payload) return "toggle 缺少状态 key";
    return stateHasPath(context.statePaths, payload) ? null : `initialState 中不存在状态 “${payload}”`;
  }
  if (type === "submit") {
    if (!payload) return "submit 缺少 formId";
    if (!formExists(context.source, payload)) return `未找到表单 “${payload}”`;
    return declaredHandler !== undefined ? null : `actions 中不存在提交处理器 “${action}”`;
  }
  if (type === "close-modal") return null;
  return declaredHandler !== undefined ? null : `未找到 action 处理器 “${action}”`;
}

function inspect(source) {
  const pages = extractObject(source, "pages");
  const modals = extractObject(source, "modals");
  const initialState = extractObject(source, "initialState");
  const actions = extractObject(source, "actions");
  const points = extractInteractionPoints(source);
  const context = {
    source,
    pageKeys: pages.keys,
    modalKeys: modals.keys,
    statePaths: initialState.paths,
    actionKeys: actions.keys,
    actionEntries: actions.entries
  };

  const failures = [];
  let bound = 0;
  for (const [name, declaration] of [
    ["pages", pages],
    ["modals", modals],
    ["initialState", initialState],
    ["actions", actions]
  ]) {
    if (!declaration.found) failures.push({ tag: "script", line: 1, source: name, reason: `缺少 ${name} 对象声明` });
  }
  points.forEach(point => {
    if (point.action !== undefined) {
      const reason = checkAction(point, context);
      if (reason) failures.push({ ...point, reason });
      else bound += 1;
      return;
    }
    if (point.runtimeBinding) {
      bound += 1;
      return;
    }
    if (point.href !== undefined) {
      const href = point.href.trim();
      if (!href || href === "#" || /^javascript:/i.test(href)) {
        failures.push({ ...point, reason: "href 为空、仅为 # 或使用 javascript:，不能视为有效交互" });
      } else bound += 1;
      return;
    }
    failures.push({ ...point, reason: "缺少 data-action、运行时数据绑定或 href" });
  });

  const tabCounts = new Map();
  for (const match of source.matchAll(/\bdata-tab-(?:button|panel)\s*=\s*["']([^"']+)["']/g)) {
    const key = match[1];
    tabCounts.set(key, (tabCounts.get(key) || 0) + 1);
  }
  tabCounts.forEach((count, key) => {
    if (count !== 2) failures.push({ tag: "tab", line: 1, source: key, reason: `Tab 标识应各有一个按钮和面板，实际命中 ${count} 次` });
  });

  points.filter(point => point.runtimeBinding === "data-sort").forEach(point => {
    const key = String(point.bindingValue || "").trim();
    if (!key) return;
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (!new RegExp(`\\bdata-${escaped}\\s*=`, "i").test(source)) {
      failures.push({ ...point, reason: `排序字段 “${key}” 没有对应的 data-${key} 数据源` });
    }
  });

  for (const match of source.matchAll(/<[^>]+\bdata-list-item\b[^>]*>[\s\S]*?<button\b([^>]*)\bdata-action=["']navigate:[^"']+["']([^>]*)>/gi)) {
    const attributes = parseAttributes(`<button ${match[1]} ${match[2]}>`);
    if (!attributes.has("data-params")) {
      failures.push({ tag: "button", line: lineNumber(source, match.index), source: match[0].slice(0, 160), reason: "列表行跳转缺少 data-params，无法携带记录上下文" });
    }
  }

  return {
    total: points.length,
    bound,
    failures,
    declarations: {
      pages: [...pages.keys],
      modals: [...modals.keys],
      state: [...initialState.paths],
      actions: [...actions.keys]
    }
  };
}

function printReport(filePath, report) {
  console.log("交互完整性检查报告");
  console.log(`文件: ${filePath}`);
  console.log(`总交互点数: ${report.total}`);
  console.log(`已绑定处理逻辑: ${report.bound}`);
  console.log(`未绑定交互点: ${report.failures.length}`);
  console.log("");
  console.log("未绑定的交互点列表（点击不生效的元凶）:");
  if (!report.failures.length) {
    console.log("- 无");
  } else {
    report.failures.forEach(item => {
      const label = item.action ? `data-action=\"${item.action}\"` : item.source;
      console.log(`- 第 ${item.line} 行 <${item.tag}> ${label}: ${item.reason}`);
    });
  }
  console.log("");
  console.log(report.failures.length ? "结果: 未通过" : "结果: 通过");
}

function main() {
  const input = process.argv[2];
  if (!input || input === "--help" || input === "-h") {
    usage();
    process.exitCode = input ? 0 : 2;
    return;
  }

  const filePath = path.resolve(process.cwd(), input);
  let source;
  try {
    source = fs.readFileSync(filePath, "utf8");
  } catch (error) {
    console.error(`无法读取原型 HTML: ${filePath}`);
    console.error(error.message);
    process.exitCode = 2;
    return;
  }

  const report = inspect(source);
  printReport(filePath, report);
  process.exitCode = report.failures.length ? 1 : 0;
}

if (require.main === module) main();

module.exports = { inspect };
