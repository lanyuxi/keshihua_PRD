#!/usr/bin/env node
// Execute the actual review loader against original browser drafts and newer saves.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../assets/container-template.html'), 'utf8');
const start = source.indexOf('      async function loadPersistedState()');
const end = source.indexOf('      function persistState()', start);
assert(start >= 0 && end > start, 'Review loader unavailable');
const loader = source.slice(start, end);
const original = {docs: {architecture: '原版已编辑需求'}, activeDoc: 'architecture', mode: 'floating', leftWidth: 420, rightWidth: 320, savedAt: '2026-01-02T00:00:00Z'};

async function load(local, database, embedded = null) {
  const state = {docs: {architecture: '初始需求'}, mode: 'review', leftWidth: 360, rightWidth: 360};
  const nodes = {'#review-state': {textContent: JSON.stringify(embedded)}, '#disk-save': {}, '#save-state': {}};
  const context = vm.createContext({JSON, Number, window: {showOpenFilePicker() {}}, state, revision: 0, fileHandle: null, STORAGE_KEY: 'fixture', $: key => nodes[key], localStorage: {getItem: () => JSON.stringify(local)}, storedValue: async key => key === 'fixture' ? database : null});
  vm.runInContext(loader + ';this.load = loadPersistedState;', context);
  await context.load();
  return state;
}

(async () => {
  const migrated = await load(original, null);
  assert.equal(migrated.docs.architecture, '原版已编辑需求');
  assert.equal(migrated.mode, 'floating');
  assert.equal(migrated.leftWidth, 420);
  assert.equal(migrated.rightWidth, 320);
  const newer = {docs: {architecture: '较新的完整草稿'}, savedAt: '2026-01-03T00:00:00Z'};
  assert.equal((await load(original, newer)).docs.architecture, '较新的完整草稿');
  assert.equal((await load(original, {...newer, savedAt: '2026-01-01T00:00:00Z'})).docs.architecture, '原版已编辑需求');
  const file = {docs: {architecture: '最新磁盘文件'}, savedAt: '2026-01-04T00:00:00Z'};
  assert.equal((await load(original, newer, file)).docs.architecture, '最新磁盘文件');
  const invalid = await load({...original, mode: 'invalid', leftWidth: '420', rightWidth: null}, null);
  assert.equal(invalid.mode, 'review');
  assert.equal(invalid.leftWidth, 360);
  assert.equal(invalid.rightWidth, 360);
  console.log('PASS: original drafts restore; newer saves win; invalid mode and widths are ignored');
})().catch(error => { console.error(error); process.exitCode = 1; });
