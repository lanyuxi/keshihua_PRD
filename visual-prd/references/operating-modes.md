# 工作模式与交接契约

根据用户已有材料选择最小路径，不要为了使用生成器而重写可用产物。

## 模式选择

### assemble：装配模式

用户已经有以下三项：

- Markdown PRD；
- 已包含标注占位的原型源文件；
- 与 `data-anno` 一一对应的标注 JSON。

原型源文件应包含 `/*__ANNOTATION_RUNTIME__*/` 和 `__ANNOTATION_DATA__` 占位。构建器只做校验、运行时内联和三栏装配，不改业务页面。

### enhance：增强模式

用户有普通离线 HTML 原型，但原型尚未接入标注运行时。若已具备标注 JSON 和一一对应的 `data-anno` 锚点，可直接构建；若两者缺失，先按 [现有原型从零建立标注](bootstrap-existing.md) 从可核对材料建立标注计划，在原型**工作副本**中添加锚点并生成 `annotations.json`，再交给构建器。构建器只负责装配，不负责猜测业务规则或自动选择标注位置。

有 Markdown PRD 时用原文作为说明依据；只有原型时先创建明确标注“待产品确认”的原型观察记录作为 `inputs.prd`，只描述可核对的界面与交互，不编造业务规则。没有真实标注时不能交付只有三栏外壳的评审页。

已有原型继续使用自己的脚本、路由和样式。仅在原型本身已经引用 `prototype-runtime.js` 时才内联该运行时，禁止无条件注入第二套交互逻辑。

多页面原型应在页面切换时更新 `body[data-anno-page]`。单页面原型可在项目清单中设置 `page_id`；未设置时从标注数据推断。

### generate：生成模式

用户只有需求、会议记录或产品想法。先创建并确认 `product-model.json`，再由脚本派生 PRD、原型和标注。需要复用现有产品视觉时附加 `ui-profile.json`。

默认组件是评审起点，不是最终视觉稿；声明式组件无法表达关键交互时使用 `custom` 或用户自己的 HTML。

## 项目清单

从 `assets/project-manifest-template.json` 创建 `visual-prd.project.json`。路径相对清单文件解析，输出目录不得覆盖任一输入文件。

装配或增强模式：

```json
{
  "schema_version": "1.0",
  "mode": "enhance",
  "output_dir": "dist",
  "inputs": {
    "prd": "prd.md",
    "prototype": "prototype.html",
    "annotations": "annotations.json"
  },
  "prototype": { "page_id": "list" }
}
```

生成模式：

```json
{
  "schema_version": "1.0",
  "mode": "generate",
  "output_dir": "dist",
  "inputs": {
    "product_model": "product-model.json",
    "ui_profile": "ui-profile.json"
  }
}
```

运行：

```bash
python3 scripts/build-review.py visual-prd.project.json
```

## 编辑、流程图与开发页面导出

三种模式的 `inputs` 均支持可选 `"flows": "flows.md"`。该 Markdown 应包含可读的 Mermaid 围栏源码与文字说明；构建后提供产品概述后的流程图栏目。具体编辑、授权写回和下载边界见 [编辑与导出指南](editing-and-export.md)。

## 输出约定

所有模式都输出：

- `prototype-source.html`：可继续修改的原型源副本；
- `prototype.html`：运行时已内联的独立原型；
- `visual-prd.html`：唯一主交付，同时包含三栏评审与浮动标注两种可切换模式；
- `build-report.json`：模式、输入、校验和产物清单。

生成模式另外输出 `prd.md` 与 `annotations.json`；使用界面规范时输出 `ui-profile-preview.html`。

`build-report.json` 必须包含 `primary_artifact`，交付时只能打开该路径。不得为多页原型另行手写一份同名容器；如需扩展导航，应扩展标准模板或输入协议后重新构建。交付前运行：

```bash
python3 scripts/validate-review-artifact.py dist/visual-prd.html
```

## 模式边界

- 不把界面规范强制应用到已有 HTML。
- 不因装配而改写用户原文件。
- 不把产品模型设为装配模式的必填项。
- 不把默认 PRD 模板或通用后台组件描述为适合所有业务。
- 不为特殊组件虚构结构；保留用户实现或明确标记待适配。
