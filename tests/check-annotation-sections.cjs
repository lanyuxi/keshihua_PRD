const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const {chromium} = require('playwright');

const source = fs.readFileSync(process.argv[2], 'utf8');
const legacy = source.replace(/(const ANNOTATIONS_PAYLOAD = ")([^"]+)"/, (_, prefix, payload) => {
  const annotations = JSON.parse(Buffer.from(payload, 'base64').toString());
  const rows = annotations.filter(item => item.pageId === 'list');
  rows[0].sections = {...rows[0].sections, sorting: '旧规则：按更新时间倒序'};
  rows[1].sections = {...rows[1].sections, sorting: '旧规则：同一时间按编号排序'};
  rows[2].sections = {...rows[2].sections, sorting: rows[0].sections.sorting};
  return prefix + Buffer.from(JSON.stringify(annotations)).toString('base64') + '"';
}).replace(/(const PAGE_NOTES_PAYLOAD = ")([^"]+)"/, (_, prefix, payload) => {
  const notes = JSON.parse(Buffer.from(payload, 'base64').toString());
  delete notes.list.sorting;
  return prefix + Buffer.from(JSON.stringify(notes)).toString('base64') + '"';
});
const legacyAnnotations = JSON.parse(Buffer.from(legacy.match(/const ANNOTATIONS_PAYLOAD = "([^"]+)"/)[1], 'base64').toString());
const legacySaved = source.replace('id="review-state" type="application/json">null', () =>
  'id="review-state" type="application/json">' + JSON.stringify({annotations: legacyAnnotations, pageNotes: {list: {overview: '旧页面说明'}}, savedAt: '2026-01-01T12:00:00.000Z'}));
let saved;
const server = http.createServer((req, res) => {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(req.url === '/saved' ? saved : req.url === '/legacy' ? legacy : req.url === '/legacy-saved' ? legacySaved : source);
});

async function main() {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({executablePath: process.env.CHROME_EXECUTABLE});
  try {
    const context = await browser.newContext({viewport: {width: 1640, height: 980}});
    const page = await context.newPage();
    page.setDefaultTimeout(4500);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    if (process.argv.includes('--seeded')) {
      await page.goto(url);
      await page.locator('#annotation-page-notes').getByText('点击可排序的表头切换排序。', {exact: true}).waitFor();
    }
    await page.goto(url + '/legacy');
    await page.locator('[data-edit-annotation="task-overview"]').waitFor();
    const frame = page.frameLocator('#prototype-frame');
    const card = page.locator('#annotation-list [data-annotation-id="task-overview"]');
    assert.deepEqual(await page.locator('#annotation-page-notes .annotation-section-label').allTextContents(), ['页面概述', '解决问题', '权限说明', '数据排序']);
    assert.deepEqual(await card.locator('.annotation-section-label').allTextContents(), ['交互', '流转状态', '字段列表']);
    assert.equal(await page.locator('.right-panel .eyebrow, #annotation-list article footer').count(), 0);
    const pageNotes = page.locator('#annotation-page-notes');
    assert.equal(await pageNotes.getByText('旧规则：按更新时间倒序', {exact: true}).count(), 1);
    await pageNotes.getByText('旧规则：同一时间按编号排序', {exact: true}).waitFor();
    if (process.argv.includes('--seeded')) {
      await page.locator('#annotation-page-notes table').getByText('团队负责人').waitFor();
      await card.locator('table').getByText('负责人', {exact: true}).waitFor();
      assert.deepEqual(await card.locator('table th').allTextContents(), ['区域', '字段名称', '字段逻辑', '备注']);
    }
    if (process.env.PREVIEW_SCREENSHOT) await page.screenshot({path: process.env.PREVIEW_SCREENSHOT});
    const dot = frame.locator('.anno-dot[data-annotation-id="task-overview"]');
    assert.equal((await dot.innerText()).trim(), await card.locator('.annotation-number').innerText());
    await dot.click();
    await card.and(page.locator('.is-active')).waitFor();
    await page.locator('#edit-annotation-page').click();
    assert.equal(await page.locator('#annotation-page-sorting').inputValue(), '旧规则：按更新时间倒序\n\n旧规则：同一时间按编号排序');
    for (const [id, value] of Object.entries({overview:'任务页面概述', problem:'减少重复查找', permissions:'仅展示可访问的任务', sorting:'按更新时间倒序'})) {
      await page.locator(`#annotation-page-${id}`).fill(value);
    }
    await page.locator('#annotation-editor-close').click();
    assert((await page.locator('#annotation-page-notes').innerText()).includes('减少重复查找'));
    await page.locator('[data-edit-annotation="task-overview"]').click();
    assert((await page.locator('#annotation-body').inputValue()).trim(), '旧正文保留在可编辑的交互模块');
    await page.locator('#annotation-body').fill('点击列表项查看详情');
    await page.locator('#annotation-status').fill('待处理 → 已完成');
    await page.locator('#annotation-fields').fill('| 区域 | 字段 |\n| --- | --- |\n| 列表字段 | 负责人 |');
    assert.equal(await page.locator('#annotation-sorting').count(), 0);
    await page.locator('#annotation-editor-close').click();
    await card.locator('table').waitFor();
    assert.deepEqual(await card.locator('table th').allTextContents(), ['区域', '字段名称', '字段逻辑', '备注']);
    assert.deepEqual(await card.locator('table tbody td').allTextContents(), ['列表字段', '负责人', '', '']);
    await page.locator('[data-edit-annotation="task-overview"]').click();
    assert.match(await page.locator('#annotation-fields').inputValue(), /\| 区域 \| 字段名称 \| 字段逻辑 \| 备注 \|/);
    await page.locator('#annotation-fields').fill('| 区域 | 字段 | 备注 |\n| --- | --- | --- |\n| 列表字段 | 负责人 | 旧备注 |');
    assert.deepEqual(await card.locator('table tbody td').allTextContents(), ['列表字段', '负责人', '', '旧备注']);
    await page.locator('#annotation-fields').fill('| 区域 | 字段名称 | 字段逻辑 | 备注 |\n| --- | --- | --- | --- |\n| 列表字段 | 负责人 | 当前处理人 | 支持筛选 |');
    await page.locator('#annotation-editor-close').click();
    await pageNotes.getByText('按更新时间倒序', {exact: true}).waitFor();
    assert(!(await card.innerText()).includes('按更新时间倒序'));
    await page.locator('#page-select').selectOption('detail');
    await page.waitForFunction(() => document.querySelector('#annotation-summary').textContent.includes('任务详情'));
    assert(!(await page.locator('#annotation-page-notes').innerText()).includes('减少重复查找'));
    assert(!(await pageNotes.innerText()).includes('按更新时间倒序'));
    await page.locator('#page-select').selectOption('list');
    await card.waitFor();
    await page.evaluate(async () => {
      window.testFile = await (await navigator.storage.getDirectory()).getFileHandle('review.html', {create: true});
      window.showOpenFilePicker = async () => [window.testFile];
    });
    await page.locator('#disk-save').click();
    await page.waitForFunction(() => document.querySelector('#save-state').textContent.startsWith('已自动写回'));
    saved = await page.evaluate(async () => (await window.testFile.getFile()).text());
    const snapshot = JSON.parse(saved.match(/<script[^>]*id="review-state"[^>]*>(.*?)<\/script>/s)[1]);
    assert.equal(snapshot.pageNotes.list.permissions, '仅展示可访问的任务');
    assert.equal(snapshot.pageNotes.list.sorting, '按更新时间倒序');
    const clean = await browser.newContext();
    const reopened = await clean.newPage();
    await reopened.goto(url + '/saved');
    await reopened.locator('#annotation-list [data-annotation-id="task-overview"] table').waitFor();
    assert.deepEqual(await reopened.locator('#annotation-list [data-annotation-id="task-overview"] table tbody td').allTextContents(), ['列表字段', '负责人', '当前处理人', '支持筛选']);
    await reopened.locator('#annotation-page-notes').getByText('仅展示可访问的任务', {exact: true}).waitFor();
    await reopened.locator('#annotation-page-notes').getByText('按更新时间倒序', {exact: true}).waitFor();
    assert((await reopened.locator('#annotation-list').innerText()).includes('待处理 → 已完成'));
    const download = page.waitForEvent('download');
    await page.locator('#download-page').click();
    const developer = fs.readFileSync(await (await download).path(), 'utf8');
    assert(!developer.includes('按更新时间倒序') && !developer.includes('减少重复查找'));
    await page.locator('#mode-toggle').click();
    await dot.click();
    await frame.locator('.anno-panel:visible').waitFor();
    assert(!(await frame.locator('.anno-panel:visible').innerText()).includes('旧规则：按更新时间倒序'));
    await page.locator('#mode-toggle').click();
    await page.locator('#add-annotation').click();
    const heading = await frame.getByRole('heading', {name: '任务看板', exact: true}).boundingBox();
    await page.mouse.click(heading.x + heading.width / 2, heading.y + heading.height / 2);
    await page.locator('#annotation-editor-dialog[open]').waitFor();
    assert.match(await page.locator('#annotation-fields').inputValue(), /^\| 区域 \| 字段名称 \| 字段逻辑 \| 备注 \|/);
    await page.locator('#annotation-title').fill('新增状态标注');
    await page.locator('#annotation-status').fill('提交后待处理');
    await page.locator('#annotation-editor-close').click();
    const added = page.locator('#annotation-list article').filter({hasText: '新增状态标注'});
    await added.getByText('提交后待处理', {exact: true}).waitFor();
    await added.getByRole('button', {name: /删除标注/}).click();
    await page.locator('#annotation-delete-confirm').click();
    await added.waitFor({state: 'detached'});
    assert((await page.locator('#annotation-page-notes').innerText()).includes('减少重复查找'));
    await page.locator('#edit-annotation-page').click();
    await page.locator('#annotation-page-sorting').fill('');
    await page.locator('#annotation-editor-close').click();
    await page.reload();
    await page.locator('[data-edit-annotation="task-overview"]').waitFor();
    assert(!(await pageNotes.innerText()).includes('旧规则：'));
    await page.goto(url + '/legacy-saved');
    await pageNotes.getByText('旧页面说明', {exact: true}).waitFor();
    await pageNotes.getByText('旧规则：按更新时间倒序', {exact: true}).waitFor();
    assert.deepEqual(errors, []);
    console.log('PASS page sorting migration, card cleanup, link, editing, page isolation, disk reopen, clean export and floating detail');
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => server.close());
