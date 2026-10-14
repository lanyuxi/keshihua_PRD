#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const vm = require("node:vm");

const filePath = process.argv[2];
if (!filePath) {
  console.error("用法: node check-generated-behavior.js <generated-prototype.html>");
  process.exit(2);
}

function fail(message) {
  console.error(`FAIL: ${message}`);
  process.exit(1);
}

const source = fs.readFileSync(filePath, "utf8");
const blocks = [...source.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(match => match[1]);
const generated = blocks.find(block => block.includes("const initialState") && block.includes("const submitSpecs"));
if (!generated) fail("未找到生成模式的数据与提交处理代码");

const placeholderNode = {
  innerHTML: "",
  textContent: "",
  classList: { add() {}, remove() {} }
};
const context = {
  console,
  document: {
    querySelector() { return placeholderNode; },
    createElement() { throw new Error("定义阶段不应创建动态列表节点"); }
  },
  window: { __proto: { closeModal() {} } },
  setTimeout() {},
  Date,
  Math,
  Object,
  JSON,
};
context.globalThis = context;

try {
  vm.runInNewContext(`${generated}\n;globalThis.__audit = { initialState, submitSpecs, actions };`, context, { timeout: 2000 });
} catch (error) {
  fail(`生成代码不能执行：${error.message}`);
}

const { initialState, submitSpecs, actions } = context.__audit;
let checked = 0;
for (const [modalId, spec] of Object.entries(submitSpecs)) {
  if (spec.operation !== "append") continue;
  const target = spec.target_list;
  const before = initialState.lists?.[target]?.items;
  if (!Array.isArray(before)) fail(`弹层 ${modalId} 的目标列表 ${target} 不存在 state items`);
  const values = {};
  for (const value of Object.values(spec.record || {})) {
    if (typeof value !== "string") continue;
    for (const match of value.matchAll(/\{([A-Za-z][A-Za-z0-9_-]*)\}/g)) values[match[1]] = `测试-${match[1]}`;
  }
  const handler = actions[`submit:${modalId}-form`];
  if (typeof handler !== "function") fail(`弹层 ${modalId} 缺少提交处理器`);
  const state = JSON.parse(JSON.stringify(initialState));
  const patch = handler({ values, state });
  const after = patch?.lists?.[target]?.items;
  if (!Array.isArray(after) || after.length !== before.length + 1) fail(`弹层 ${modalId} 提交后没有向 ${target} 新增一条记录`);
  const created = after.at(-1);
  if (!created?.id) fail(`弹层 ${modalId} 新增记录缺少 id`);
  for (const [key, expected] of Object.entries(values)) {
    if (Object.prototype.hasOwnProperty.call(spec.record, key) && created[key] !== expected) {
      fail(`弹层 ${modalId} 新增记录字段 ${key} 未使用表单值`);
    }
  }
  const cleared = patch?.drafts?.[modalId] || {};
  if (Object.values(cleared).some(value => value !== "")) fail(`弹层 ${modalId} 创建成功后没有清空草稿`);
  checked += 1;
}

if (!checked) {
  console.log("PASS: 当前模型没有 append 创建表单；列表追加行为不适用");
} else {
  console.log(`PASS: ${checked} 个创建表单均真实追加列表记录并清空草稿`);
}
