#!/usr/bin/env node
// Run the actual template functions with controlled permissions and writable streams.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const template = fs.readFileSync(path.join(__dirname, '../assets/container-template.html'), 'utf8');
const source = template.slice(template.indexOf('      function persistState()'), template.indexOf('      function showToast('));
function fixture() {
  const ui = {}, writes = [], messages = [];
  let permission = 'granted', failure = false;
  const handle = {name: 'existing.html', queryPermission: async () => permission, requestPermission: async () => permission,
    createWritable: async () => ({write: async text => {if (failure) throw Error('disk-full'); writes.push(JSON.parse(text));}, close: async () => {}, abort: async () => {}})};
  const context = vm.createContext({Date, JSON, Blob, Error, DOMException, state: {docs: {overview: 'before'}}, handle,
    window: {showOpenFilePicker: async options => {assert.equal(options.multiple, false); return [handle];}},
    $: id => ui[id] ||= {textContent: ''}, storedValue: async () => {}, localStorage: {setItem() {}},
    showToast: text => messages.push(text), reviewSnapshot: () => context.state, reviewHtml: snapshot => JSON.stringify(snapshot)});
  vm.runInContext('let revision=0,diskRevision=0,fileHandle=null,saveQueue=Promise.resolve(); const STORAGE_KEY="test";' + source +
    ';this.api={persistState,flushSave,authorizeDiskSave,status:()=>({revision,diskRevision,fileHandle})};', context);
  return {context, api: context.api, ui, writes, messages, handle, permission: value => permission=value, fail: value => failure=value};
}
(async () => {
  const f = fixture();
  // No timers are provided: editing must schedule the save immediately.
  await f.api.authorizeDiskSave();
  assert.equal(f.api.status().fileHandle, f.handle);
  assert.equal(f.writes.length, 1);
  f.writes.length = 0;
  f.context.state.docs.overview = 'first'; const first = f.api.persistState();
  f.context.state.docs.overview = 'second'; const second = f.api.persistState();
  f.context.state.docs.overview = 'latest'; const latest = f.api.persistState();
  await Promise.all([first, second, latest]);
  assert.equal(f.writes.length, 1, 'superseded queued revisions must not overwrite newer edits');
  assert.equal(f.writes[0].docs.overview, 'latest');
  assert.equal(f.api.status().revision, f.api.status().diskRevision);
  f.context.window.showOpenFilePicker = async () => {throw new DOMException('cancel', 'AbortError');};
  await f.api.authorizeDiskSave();
  assert.equal(f.api.status().fileHandle, f.handle, 'cancel must preserve the existing target');
  f.context.window.showOpenFilePicker = async () => [{requestPermission: async () => 'denied'}];
  await f.api.authorizeDiskSave();
  assert.equal(f.api.status().fileHandle, f.handle, 'denial must preserve the existing target');
  f.permission('denied'); await f.api.persistState();
  assert(f.ui['#save-state'].textContent.includes('需要重新授权'));
  assert(f.api.status().diskRevision < f.api.status().revision);
  f.permission('granted'); f.fail(true); await f.api.persistState();
  assert(f.ui['#save-state'].textContent.includes('磁盘写回失败'));
  assert(f.api.status().diskRevision < f.api.status().revision);
  f.fail(false); await f.api.flushSave();
  assert(f.ui['#save-state'].textContent.includes('已自动写回'));
  assert.equal(f.api.status().diskRevision, f.api.status().revision);
  console.log('PASS: existing-file selection, immediate writes, queue coalescing, cancellation, denial and failure recovery');
})().catch(error => {console.error(error); process.exitCode=1;});
