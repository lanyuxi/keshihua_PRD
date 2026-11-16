# 可视化 PRD 4.2.4 WorkBuddy 发布字段验证

验证日期：2026-11-16。

## 问题与修复

用户上传 4.2.3 后，WorkBuddy 要求 SKILL.md 的 YAML frontmatter 提供五项字段。旧版本号仅位于 metadata 下，中英文发布字段不全；旧校验器还会把嵌套字段和顶层字段混在一起，无法发现发布格式缺失。

4.2.4 使用同一份技能元数据生成两个分发包：

- `visual-prd-4.2.4-workbuddy.zip`：WorkBuddy 专用，顶层包含以下五项字段。
- `visual-prd-4.2.4.zip`：通用技能格式，用于本机安装／SkillHub，仍使用 metadata 保存扩展信息。

| WorkBuddy 顶层字段 | 实际值或来源 |
| --- | --- |
| version | 字符串 `4.2.4`，与 metadata.version 一致 |
| display_name | 可视化 PRD |
| display_name_en | Visual PRD |
| description_zh | 完整复用技能的中文 description |
| description_en | 技能元数据中的英文描述 |

两个包的 SKILL.md 正文一致，其余 61 个文件逐字节相同。打包器只在内存中生成专用 frontmatter，不改写通用技能入口，不新增运行时依赖。

## 实际交付体积

| 包 | ZIP 字节数 | 解压后所有文件总字节数 |
| --- | ---: | ---: |
| WorkBuddy 专用包 | 2,287,525 | **3,141,204** |
| 通用包 | 2,287,489 | 3,140,321 |

两个包均为 62 个 UTF-8 文本文件，根目录直接包含 SKILL.md；低于 ZIP 3,000,000 字节和解压后 3,145,728 字节限制。WorkBuddy 包剩余 4,524 字节额度。解压大小按最终生成内容计算，包括新增的五项发布字段，不能使用生成前源目录大小代替。

## 新鲜验证

- 新增 `tests/check-workbuddy-package.py`，先对 4.2.3 实际 ZIP 运行，复现五个顶层字段缺失；对 4.2.4 实际 ZIP 运行通过。
- 使用独立 YAML 解析核对五项非空字符串、版本一致性、中文名称与中英文描述；校验 ZIP 中其余文件等于定稿源码，SKILL.md 正文未因打包而变化。
- 负向检查：缺少英文描述、顶层版本不合法但嵌套版本正确、缺少某个发布字段，校验器均拒绝。
- 通用技能通过 skill-creator 的 quick_validate，保留本机技能 frontmatter 格式。
- 两种包均通过完整 `validate-package.py`，包括脚本语法、模板、装配／增强／生成和烟雾构建。
- 从最终 WorkBuddy 包解压到干净目录，运行完整校验和真实项目构建通过；生成的完整评审 HTML 与 4.2.3 **逐字节一致**，SHA256 为 `253cb6eb71a284275e9d99014ecb07f36ed079c2e46c5ef8fb0b76f8f4e73c96`。
- 在临时副本中把普通技能目录填充至解压上限，再生成含发布字段的 WorkBuddy 包；打包器因实际解压内容超限而拒绝，且未写出 ZIP。
- 从 WorkBuddy 包解压后再次执行 --workbuddy 打包，结果与发布包逐字节一致，未累积重复字段。
- 相比 4.2.3 仅修改技能发布说明、元数据、打包和校验脚本；原有 62 个文件全部保留，其余 59 个文件逐字节不变。原版功能、图片与完整离线依赖保留。

本次未修改评审运行时，没有重新扩大浏览器回归；以完整 HTML 字节一致确认页面行为和呈现未变。原有 Python 转义 SyntaxWarning 保留。本地验证覆盖用户提供的字段和体积要求，未代用户提交 WorkBuddy 服务端审核。

WorkBuddy ZIP SHA256：`7502c0875317a3f7d24c36d9555d6b406a6285cd2685862beb9070b3cb23e79a`。

通用 ZIP SHA256：`1f061ac4fcd802fb209758394de4cfcca3ef9d2a7e2c30ded1eb3f70916b5e43`。
