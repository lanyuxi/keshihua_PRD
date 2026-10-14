# 单一产品模型与低冗余工作流

## 适用范围

本文件只适用于生成模式。已有 PRD 或原型时优先使用装配或增强模式，不要先把现有材料重写为产品模型。

## 目的

默认只编写 `product-model.json`。PRD、标注数据、通用原型结构和最终容器均由脚本派生，避免把同一条业务规则分别写进文档、HTML 和标注 JSON。

## 单一事实源

- `requirements[]`：功能描述、用户故事、状态机及其引用关系。
- `rules[]`：业务规则正文，只在这里定义一次。
- `acceptance_criteria[]`：验收口径，只在这里定义一次。
- `prototype.pages[]`：页面及声明式组件，不重复整篇 PRD。
- `prototype.navigation_annotation`：可选的跨页面导航标注，`pageId` 由编译器固定为 `*`。
- `annotation.rule_refs[]` 与 `annotation.acceptance_refs[]`：只保存引用；编译时解析正文。
- `annotation.order`：编号唯一来源。原型圆点和侧栏不得自行计算编号。

模型格式以 [product-model.schema.json](product-model.schema.json) 为准；跨字段引用、编号连续性和组件约束由 `scripts/validate-model.py` 执行。

## 推荐执行方式

```bash
python3 scripts/build-project.py product-model.json --output-dir dist
```

需要贴近现有产品的常用组件时，额外传入一次性复用的界面规范：

```bash
python3 scripts/build-project.py product-model.json --ui-profile ui-profile.json --output-dir dist
```

界面规范不复制进每个页面或组件。页面仅在确有差异时通过 `appearance` 选择结构变体。

该命令生成：

- `prd.md`
- `annotations.json`
- `prototype-source.html`
- `prototype.html`
- `visual-prd.html`
- `build-report.json`

不要在对话中粘贴上述完整派生产物；返回文件链接、关键决策与简短检查报告即可。

## 增量修改

修改某一页面时，只加载：

1. `product`、相关角色；
2. 该页面引用的模块、需求、规则和验收条件；
3. 对应的 `prototype.pages[]` 及关联弹层。

修改后仍对完整模型执行校验和构建。不得复制一份页面规则作为“局部版本”。

## 声明式组件与逃生口

优先使用 `hero`、`stats`、`table`、`tabs`、`cards`、`timeline`、`text`。只有现有组件无法表达关键交互时才使用 `custom`，其 `html` 仍必须遵守 `data-action` 和标注锚点约束，并通过交互检查。

复杂定制交互可以基于 `assets/prototype-template.html` 手工实现，继续使用同一 `product-model.json` 派生 PRD 和标注。该方式是兼容路径，不是默认路径。

默认生成器是评审脚手架，不是适用于所有业务的页面库。复杂行业组件、画布、地图、富文本或复杂图表应使用 `custom` 或已有原型，不要继续堆叠所谓通用组件。

## 交互数据契约

- 列表行跳转使用 `row_action` 指向页面，并用 `row_params` 显式声明记录参数；例如 `"row_params": {"taskId": "{id}"}`。生成器把参数写入 `data-params`，详情页通过 `state.route.params` 读取。
- 列表数据存放在 `state.lists.<listId>.items`。筛选、搜索、排序和新增记录都读取同一数组，禁止另外维护一份静态列表。
- 创建类表单使用 `submit.operation: "append"`，同时声明 `target_list` 和覆盖目标列表列的 `record` 模板。`$auto` 生成记录 ID，`{fieldName}` 引用表单值。
- 只保存表单状态时使用 `submit.operation: "save"`。未声明 `append` 的表单不得显示“已创建”或声称列表已经更新。
- `action`、Tab ID、字段名、列表 ID、排序字段和提交目标必须在构建前通过模型校验；生成器不为缺失 action 提供静默兜底。

## 审阅编辑边界

容器内 `contenteditable` 修改是本地评审副本，不会自动反向改写产品模型。需要固化的修改应回写 `product-model.json` 后重新构建，避免派生产物变成第二事实源。
