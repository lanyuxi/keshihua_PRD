#!/usr/bin/env node
// Verify the real applier can run independently in exported developer pages.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const context = {window: {}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'prototype-text-runtime.js'), 'utf8'), context);
const text = {nodeType: 3, nodeValue: '原表头'};
const icon = {nodeType: 1};
const element = {childNodes: [icon, text]};
const attrs = {placeholder: '原提示'};
const input = {getAttribute: key => attrs[key], setAttribute: (key, value) => attrs[key] = value};
let observer;
const doc = {documentElement: {}, querySelector: selector => ({'#heading': element, '#input': input})[selector], defaultView: {MutationObserver: class {constructor(fn) {observer = fn;} observe() {} disconnect() {}}}};
const edits = [{selector: '#heading', textIndex: 0, original: '原表头', value: '新表头 <b>纯文本</b>'}, {selector: '#input', attribute: 'placeholder', original: '原提示', value: '新提示'}];
// A fresh VM has none of the runtime's closure variables.
const standalone = {doc, edits};
vm.runInNewContext('(' + context.window.VisualPRDPrototypeText.apply.toString() + ')(doc,edits)', standalone);
assert.equal(text.nodeValue, '新表头 <b>纯文本</b>');
assert.equal(element.childNodes[0], icon, 'text edits must preserve sibling icons');
assert.equal(attrs.placeholder, '新提示');
text.nodeValue = '原表头'; observer(); assert.equal(text.nodeValue, edits[0].value, 'rerender must restore matching copy');
text.nodeValue = '新的业务数据'; observer(); assert.equal(text.nodeValue, '新的业务数据', 'stale edits must not replace unrelated data');
edits.push({selector: '#input', attribute: 'onclick', original: undefined, value: 'unwanted'});observer();assert.equal(attrs.onclick, undefined);
console.log('PASS: standalone text applier, rerender, sibling preservation, stale-data guard and attribute limits');
