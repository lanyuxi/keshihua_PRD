const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const {chromium} = require('playwright');

const source = fs.readFileSync(process.argv[2]);
let saved;
const server = http.createServer((req, res) => {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(req.url === '/saved' ? saved : source);
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
    await page.goto(url);
    await page.locator('[data-edit-annotation="task-overview"]').waitFor();
    const frame = page.frameLocator('#prototype-frame');
    const card = page.locator('#annotation-list [data-annotation-id="task-overview"]');
    assert.deepEqual(await page.locator('#annotation-page-notes .annotation-section-label').allTextContents(), ['页面概述', '解决问题', '权限说明']);
    assert.deepEqual(await card.locator('.annotation-section-label').allTextContents(), ['交互', '流转状态', '字段列表', '数据排序']);
    if (process.argv.includes('--seeded')) {
      await page.locator('#annotation-page-notes table').getByText('团队负责人').waitFor();
      await card.locator('table').getByText('负责人', {exact: true}).waitFor();
    }
    if (process.env.PREVIEW_SCREENSHOT) await page.screenshot({path: process.env.PREVIEW_SCREENSHOT});
    const dot = frame.locator('.anno-dot[data-annotation-id="task-overview"]');
    assert.equal((await dot.innerText()).trim(), await card.locator('.annotation-number').innerText());
    await dot.click();
    await card.and(page.locator('.is-active')).waitFor();
    await page.locator('#edit-annotation-page').click();
    for (const [id, value] of Object.entries({overview:'任务页面概述', problem:'减少重复查找', permissions:'仅展示可访问的任务'})) {
      await page.locator(`#annotation-page-${id}`).fill(value);
    }
    await page.locator('#annotation-editor-close').click();
    assert((await page.locator('#annotation-page-notes').innerText()).includes('减少重复查找'));
    await page.locator('[data-edit-annotation="task-overview"]').click();
    assert((await page.locator('#annotation-body').inputValue()).trim(), '旧正文保留在可编辑的交互模块');
    await page.locator('#annotation-body').fill('点击列表项查看详情');
    await page.locator('#annotation-status').fill('待处理 → 已完成');
    await page.locator('#annotation-fields').fill('| 字段 | 含义 |\n| --- | --- |\n| 负责人 | 当前处理人 |');
    await page.locator('#annotation-sorting').fill('按更新时间倒序');
    await page.locator('#annotation-editor-close').click();
    await card.locator('table').waitFor();
    assert((await card.innerText()).includes('按更新时间倒序'));
    await page.locator('#page-select').selectOption('detail');
    await page.waitForFunction(() => document.querySelector('#annotation-summary').textContent.includes('任务详情'));
    assert(!(await page.locator('#annotation-page-notes').innerText()).includes('减少重复查找'));
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
    const clean = await browser.newContext();
    const reopened = await clean.newPage();
    await reopened.goto(url + '/saved');
    await reopened.locator('#annotation-list [data-annotation-id="task-overview"] table').waitFor();
    await reopened.locator('#annotation-page-notes').getByText('仅展示可访问的任务', {exact: true}).waitFor();
    assert((await reopened.locator('#annotation-list').innerText()).includes('待处理 → 已完成'));
    const download = page.waitForEvent('download');
    await page.locator('#download-page').click();
    const developer = fs.readFileSync(await (await download).path(), 'utf8');
    assert(!developer.includes('按更新时间倒序') && !developer.includes('减少重复查找'));
    await page.locator('#mode-toggle').click();
    await dot.click();
    await frame.locator('.anno-panel:visible').waitFor();
    assert((await frame.locator('.anno-panel:visible').innerText()).includes('按更新时间倒序'));
    await page.locator('#mode-toggle').click();
    await page.locator('#add-annotation').click();
    const heading = await frame.getByRole('heading', {name: '任务看板', exact: true}).boundingBox();
    await page.mouse.click(heading.x + heading.width / 2, heading.y + heading.height / 2);
    await page.locator('#annotation-editor-dialog[open]').waitFor();
    await page.locator('#annotation-title').fill('新增状态标注');
    await page.locator('#annotation-status').fill('提交后待处理');
    await page.locator('#annotation-editor-close').click();
    const added = page.locator('#annotation-list article').filter({hasText: '新增状态标注'});
    await added.getByText('提交后待处理', {exact: true}).waitFor();
    await added.getByRole('button', {name: /删除标注/}).click();
    await page.locator('#annotation-delete-confirm').click();
    await added.waitFor({state: 'detached'});
    assert((await page.locator('#annotation-page-notes').innerText()).includes('减少重复查找'));
    assert.deepEqual(errors, []);
    console.log('PASS seven modules, old annotation, marker linkage, editing, page isolation, disk reopen, clean export and floating detail');
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => server.close());
