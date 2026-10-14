# 需求交接契约 1.0

这是一份**数据契约，不是第四个 Skill**。它解决同一条需求跨 PRD、质量审核与产品验收时被重新编号、丢失来源或断开引用的问题。机器可读结构见同目录 `requirement-handoff.schema.json`。

三个 Skill 都能独立完成各自的任务。没有跨 Skill 交接需求时，不生成此文件，也不需要安装或运行另外两个 Skill；交接验证只是额外的可选检查，不得阻断各自的基础工作流。

## 何时使用

- 上游已有稳定需求 ID 时，沿用原 ID，例如 `FR-001`。不得为了满足下游工具而改为 `REQ-001`。
- 输入没有稳定 ID 时，首次建模者生成 `REQ-###`；后续各环节继承该 ID。
- 原需求删除或废弃时标记 `RETIRED`，不复用 ID；原有链接保留用于影响追踪。
- 独立使用质量审核或验收 Skill 时，此交接文件是可选输入，不得因此拒绝普通 PRD、Word 或 PDF。

## 单一数据源

`requirements[]` 定义需求身份与原始证据。`links[]` 是“需求 → 下游对象”的唯一关系表；不要在需求对象里再维护第二份引用列表。`target_type` 仅表示对象类别：`PROTOTYPE_ANCHOR`、`ANNOTATION`、`METRIC`、`QUALITY_ISSUE`、`ACCEPTANCE_CASE`。各下游文件保留自己的内容；交接文件只保存引用，不复制业务内容。

## 按产出顺序补齐链接

1. 需求形成时先固定需求 ID、原始来源和已有的原型、标注或指标链接；尚未产生的质量问题、验收用例不能预先编造 ID。
2. 质量检查后，将报告追踪矩阵 `issue_refs` 中的每一组“需求 ID → 问题 ID”补入 `QUALITY_ISSUE` 链接，再提供 `--quality-report` 校验。未关联具体需求的跨领域问题仍留在质量报告中，不强行建立虚假需求链接。
3. 验收用例设计后，将每个用例的 `requirement_ids` 逐条补入 `ACCEPTANCE_CASE` 链接，再提供 `--acceptance-plan` 校验。验收条件 `acceptance_criteria` 是需求内容，不等于已生成的 `UAT-###` 用例。
4. 上线前如需复查，可同时传入质量报告和验收方案。三个 Skill 仍可单独使用；阶段性没有后续产物时，不要求预建对应链接。

## 不变量

1. `requirements[].id` 唯一、非空且不含空白；相同产品的后续版本不得悄悄复用已废弃 ID。
2. `source.artifact` 必须命中 `source_artifacts[].id`；定位必须指向原始材料，不得把派生文本行号冒充源行号。
3. 每个 `links[].requirement_id` 必须命中一条需求；同一 `(requirement_id, target_type, target_id)` 不得重复。
4. 若提供原型、标注、质量报告或验收方案，链接目标必须真实存在；即使某类链接为空，也必须读取已提供的对应文件并执行该类反向检查。缺失或拼错时验证失败。
5. `RETIRED` 需求不能被新用例当成范围内有效需求；旧链接保留作为变更影响线索。
6. 质量问题使用 `QG-###`，验收用例使用 `UAT-###`；二者不是需求 ID，必须经链接指向需求。

## 执行

只检查交接文件自身：

```bash
python3 scripts/validate-handoff.py <handoff.json>
```

有下游文件时追加相应参数；验证器会检查真实锚点和 ID。传入质量报告时核对追踪矩阵的“需求 → 问题”链接；传入验收方案时核对全部用例与需求 ID 的双向链接，即使交接文件尚无该类链接也不会跳过。仅有链接、尚无对应产物时才标记为未验证：

```bash
python3 scripts/validate-handoff.py <handoff.json> \
  --prototype <prototype.html> --annotations <annotations.json> \
  --quality-report <quality.json> --acceptance-plan <acceptance.json>
```

本仓库的三个 Skill 各自携带相同版本的契约与验证器，单独分发也能使用；工作区级测试检查副本完全一致。
