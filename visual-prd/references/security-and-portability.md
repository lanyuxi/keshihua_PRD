# 安全与可移植性边界

## 信任模型

最终容器只加载由当前任务生成并经质量门禁检查的原型源码。不要把未知网页、第三方脚本或未经检查的 HTML 直接注入容器。

容器当前需要读取 `srcdoc` 原型 DOM 以定位外层兼容标注，因此 iframe 同时启用 `allow-scripts` 与 `allow-same-origin`。浏览器会对此给出沙箱能力警告；这不是对不可信内容的安全隔离方案。若输入包含外部或不可信 HTML，停止构建并改用完全基于 `postMessage` 的隔离架构。

## 数据处理

- Markdown 在渲染前进行 HTML 转义，不执行原始 HTML。
- 标注标题、正文、规则和选择器按文本处理。
- 最终交付物不得包含外部脚本、样式、字体、图片或网络请求。
- `localStorage` 只保存当前本地文件的文档编辑和原型状态；不要存储密码、令牌或个人敏感数据。

## 跨窗口通信

- 消息接收端必须校验 `event.source` 是否为预期 iframe 或父窗口。
- `file:` 与沙箱 `srcdoc` 可能使用不透明来源，因此不能只依赖 `event.origin`。
- 消息只传递路由、标注 ID 和非敏感 UI 状态，不传输用户凭据或业务密钥。

## 运行环境

- 构建需要 Python 3.10+。
- 静态交互检查需要 Node.js 18+。
- 最终 HTML 应在当前稳定版 Chrome、Edge 和 Safari 中离线打开；不支持的 API 必须有降级路径或明确提示。
- 分发前运行 `validate-package.py`、`check-interactions.js`、构建命令与浏览器级自检，并使用 `package-skill.py` 重新生成压缩包。
