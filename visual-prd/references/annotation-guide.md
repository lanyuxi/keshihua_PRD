# 原型标注指南

已有 HTML 原型**尚无标注数据或锚点**时，先按 [现有原型从零建立标注](bootstrap-existing.md) 在工作副本中准备两者；本指南说明数据与运行时协议。单纯注入运行时不会产生标注圆点。

## 目录

- [添加 data-anno 锚点](#添加-data-anno-锚点)
- [声明页面与作用域](#声明页面与作用域)
- [标注数据 JSON Schema](#标注数据-json-schema)
- [初始化工作流](#初始化工作流)
- [增量更新工作流](#增量更新工作流)
- [运行时行为与约束](#运行时行为与约束)

## 通俗中文与去重

- 直接说明使用者的动作、触发条件、页面反馈和必要例外，尽量用短句，不堆“现状/AC编号/状态码/权限键”等代码化片段。
- 可用中文解释时直接用中文。必须保留英文时，首次出现写为“Token（会话令牌）”“teachers.edit（编辑教师资料权限）”等，不能只给一个技术键让读者猜。编号与原始代码仍可保留在模型/交接资料用于追踪，不在正文重复铺陈。
- 一个要求集中说明一次：全局规则放左侧业务规则，本位置标注只补它的特殊条件或行为。不要在创建入口、列表字段和弹窗里反复复制同一段验证要求；需要关联时用中文标题指向已有说明，不删必要的业务差异。
- 用户已有正式原文的术语或含义不明确时先保留事实，标记待确认；不要自动猜译业务字段，也不要用正则机械删掉看似重复的段落。

## 管理后台标注覆盖

对实际存在的控件逐项核对三类：筛选器（字段含义、选项、组合/重置与空结果）；每一个列表或表单字段（含义、类型/格式、必填/默认值/校验及权限）；功能操作（入口、可用条件、成功结果、失败与二次确认）。没有该类控件则明确不适用，不为凑数量编造控件或规则。

生成模式可在 `columns[]`、`controls.filters[]` 和模态 `fields[]` 中声明 `annotation`，操作继续使用 `actions[].annotation`；表头字段标注在排序、筛选和界面规范切换后保留，卡片布局在独立的字段说明行放一次锚点，避免重复 ID，筛选为空时字段说明仍保留。复杂表单/现有 HTML 在真实控件上放 data-anno。说明未知时标待确认，不能以新增的空白人工标注冒充已完成规则。

## 添加 data-anno 锚点

3.0 默认不手写最终标注 JSON：在 `product-model.json` 的页面、组件、操作、表格行、Tab、弹层或字段上声明 `annotation`，由 `scripts/build-annotations.py` 解析规则和验收条件引用，并由 `scripts/build-prototype.py` 在同一节点生成 `data-anno`。只有兼容旧项目或自定义复杂原型时才直接维护下述 HTML 与 JSON。

```json
"annotation": {
  "id": "project-create",
  "order": 2,
  "scope": { "type": "page", "id": "project-list" },
  "title": "新建项目入口",
  "rule_refs": ["RULE-001"],
  "acceptance_refs": ["AC-001"]
}
```

`rule_refs` 与 `acceptance_refs` 只保存引用，不复制正文；引用无法命中时模型校验失败。

在需要标注的真实交互元素上添加 `data-anno="标注 ID"`。该 ID 必须与标注数据中的 `id` 完全一致。

```html
<button type="button" data-anno="project-create">新建项目</button>
```

一个标注 ID 对应一个页面元素。ID 使用字母、数字、连字符或下划线，并以字母或数字开头。不要把锚点放在仅用于布局的空容器上，也不要重复使用同一个 ID。

如果标注目标由组件动态渲染，保留稳定的 `data-anno` 值；组件挂载后运行时会通过 `MutationObserver` 自动发现并定位。

## 声明页面与作用域

在 `body` 上声明当前业务页面。单页应用切换路由时同步更新该值：

```html
<body data-anno-page="project-list">
```

页面级锚点不需要额外作用域属性。Tab、抽屉或弹窗使用作用域容器：

```html
<section data-anno-scope="tab" data-anno-scope-id="members">
  <button data-anno="member-invite">邀请成员</button>
</section>

<aside data-anno-scope="drawer" data-anno-scope-id="project-detail">
  <button data-anno="project-archive">归档项目</button>
</aside>

<dialog open data-anno-scope="modal" data-anno-scope-id="archive-confirm">
  <button data-anno="archive-confirm-submit">确认归档</button>
</dialog>
```

隐藏非活动 Tab 时使用 `hidden`、`display: none` 或 `aria-hidden="true"`。运行时只扫描可见锚点，并按以下层级只显示最高层标注：

1. 弹窗 `modal`
2. 抽屉 `drawer`
3. 页面与当前 Tab `page` / `tab`

## 标注数据 JSON Schema

三种模式可用 `inputs.page_notes` 预填页面概述、解决问题和权限说明。文件示例 `{"list":{"overview":"任务列表","problem":"便于查找任务","permissions":"待确认"}}`，其中 `list` 为页面 ID。

数字标注沿用 `body`（交互）。可在标注或生成模式的 `annotation` 中加入 `sections`，填写 `status`（流转状态）、`fields`（字段列表）、`sorting`（数据排序）。支持 Markdown 表格，未知留空。右栏编辑随评审 HTML 保存。

字段列表使用四列 `| 区域 | 字段名称 | 字段逻辑 | 备注 |`，区域可填筛选器、列表字段或表单字段。字段逻辑描述展示、校验或操作规则，未知留空。

初始化和增量更新都使用以下标注对象：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "order", "pageId", "title", "body", "businessRules", "scope"],
  "additionalProperties": false,
  "properties": {
    "id": {
      "type": "string",
      "minLength": 1,
      "description": "与 data-anno 完全一致的稳定标识"
    },
    "order": {
      "type": "integer",
      "minimum": 1,
      "description": "标注在当前可见交互视图中的唯一显示编号"
    },
    "pageId": {
      "type": "string",
      "minLength": 1,
      "description": "所属页面；使用 * 表示跟随锚点所在的当前页面"
    },
    "title": {
      "type": "string",
      "minLength": 1
    },
    "body": {
      "type": "string"
    },
    "businessRules": {
      "oneOf": [
        { "type": "string" },
        { "type": "array", "items": { "type": "string" } }
      ]
    },
    "sections": {
      "type": "object",
      "additionalProperties": false,
      "properties": {"status": {"type": "string"}, "fields": {"type": "string"}, "sorting": {"type": "string"}}
    },
    "scope": {
      "type": "object",
      "required": ["type", "id"],
      "additionalProperties": false,
      "properties": {
        "type": { "enum": ["page", "tab", "drawer", "modal"] },
        "id": {
          "type": "string",
          "description": "同一作用域共享同一 ID，用于上一条和下一条切换"
        }
      }
    }
  }
}
```

示例数据：

```js
const annotations = [
  {
    id: "project-create",
    order: 1,
    pageId: "project-list",
    title: "新建项目",
    body: "点击后进入项目创建流程。",
    businessRules: [
      "仅管理员和项目负责人可见",
      "新项目默认继承组织级审批规则"
    ],
    scope: { type: "page", id: "project-list" }
  },
  {
    id: "archive-confirm-submit",
    order: 1,
    pageId: "project-list",
    title: "确认归档",
    body: "提交归档操作并关闭确认弹窗。",
    businessRules: "归档后项目进入只读状态",
    scope: { type: "modal", id: "archive-confirm" }
  }
];
```

标注编号必须由单一数据源（`order` 字段）提供，原型圆点和侧边面板均只读取该字段，禁止任何位置使用数组下标或下标加减运算生成编号。

编号按当前可见交互视图校验：

- `pageId: "*"` 的跨页面标注进入每个业务页面的基础序列，页面内标注从其最大 `order + 1` 继续。
- 页面基础标注与当前活动 Tab 的标注合并后，`order` 必须从 1 开始连续且不能重复。
- 互斥 Tab 中不会同时出现的标注可以复用同一 `order`。
- 抽屉或弹窗打开后只显示最高层级标注，并在该顶层视图内独立从 1 开始编号。
- 同一锚点在不同作用域出现时仍分别定义 `order`，但任何可能同时可见的组合不得重号。

## 初始化工作流

将运行时脚本放在原型页面底部，确保脚本执行时页面 DOM 已可用：

```html
<script src="./annotation-runtime.js"></script>
<script>
  AnnotationRuntime.init({
    annotations,
    options: {
      loopNavigation: true,
      dotOffsetX: 6,
      dotOffsetY: 6
    }
  });
</script>
```

开发阶段可以通过 `src` 引用运行时；装配最终离线交付物时，必须把 `annotation-runtime.js` 的内容内联到原型 HTML 的 `<script>` 中。

运行时按以下顺序工作：

1. 扫描所有可见的 `[data-anno]` 元素。
2. 根据 `body[data-anno-page]` 筛选当前页面。
3. 根据可见弹窗、抽屉和 Tab 计算最高层级。
4. 在锚点右上方绘制编号圆点。
5. 点击圆点打开详情，并在同一 `scope.id` 内切换上一条或下一条。

如果页面 ID 由路由器维护，也可以显式提供字符串或函数：

```js
AnnotationRuntime.init({
  annotations,
  pageId: () => router.currentRoute.value.name
});
```

## 增量更新工作流

原型已初始化后，使用 `update()` 新增、替换或删除标注，无需销毁运行时：

```js
AnnotationRuntime.update({
  upsert: [
    {
      id: "project-create",
      order: 1,
      pageId: "project-list",
      title: "新建项目",
      body: "更新后的交互说明。",
      businessRules: ["仅管理员可见"],
      scope: { type: "page", id: "project-list" }
    },
    {
      id: "project-filter",
      order: 2,
      pageId: "project-list",
      title: "项目筛选",
      body: "按状态与负责人筛选。",
      businessRules: [],
      scope: { type: "page", id: "project-list" }
    }
  ],
  remove: ["obsolete-annotation"]
});
```

- `upsert` 中 ID 已存在时使用新数据中的 `order`，不保留隐式数组位置。
- 新增或删除标注时，同时调整所有可能同屏标注的 `order`，保证当前可见视图仍从 1 开始连续且不跳号。
- `remove` 同时删除数据和对应圆点。
- 只更新 DOM 状态而不更新数据时，调用 `AnnotationRuntime.refresh()`。
- 路由器无法同步 `body[data-anno-page]` 时，调用 `AnnotationRuntime.setPage(pageId)`。

## 运行时行为与约束

- 页面滚动、窗口缩放、DOM 变化以及业务页面的 CSS 过渡和动画完成后会自动重新定位；忽略标注运行时自身圆点和面板的过渡事件，避免 hover 触发重复重绘。
- Tab 切换或弹层开关后会自动重新扫描；复杂框架场景可在状态提交后补充调用 `refresh()`。
- 右侧标注列表点击条目时，使用条目的 `data-annotation-id` 调用 `AnnotationRuntime.open(id)`，让中间原型打开对应标注；不得重新按数组位置推导 ID。
- 标注详情使用纯文本渲染，不执行数据中的 HTML。
- 业务规则为空时显示“待确认”，不要由运行时推断业务规则。
- 按 `Esc` 关闭详情；详情打开时可用左右方向键切换同一作用域标注。
- 使用 `AnnotationRuntime.getState()` 查看当前页、可见标注和活动标注。
- 页面卸载或重新注入前调用 `AnnotationRuntime.destroy()` 清理监听器和覆盖层。
- 构建器会校验标注数据与原型锚点严格一一对应；数据缺锚点、锚点缺数据或重复锚点都必须在交付前修复。
