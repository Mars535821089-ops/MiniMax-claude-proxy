# Changelog

本项目的所有重要变更都会记录在此文件。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-06-12

### ✨ 新增 (Added)
- 6 大块 Anthropic 兼容层中间件：
  - Prompt Caching：剥离 `cache_control` + SQLite 响应级缓存 + 前缀统计 + usage 占位回填
  - Extended Thinking：system 注入 `<thinking>` 引导 + 流式滚动 buffer 拆标签
  - 复杂 `tool_use` schema：`$ref` 展开 / `oneOf` `anyOf` 拍平 + 响应嵌套 JSON 还原
  - 多模态预处理：URL→base64 / PIL 自动缩放 / PyMuPDF 文本+图像提取
  - SSE 稳定性：15s 心跳 ping / `tool_use` 整块缓冲 / `cache_*_input_tokens` 占位注入 / event_id 续传
  - Server-side Tools：翻译 `web_search_20250305` / `code_execution` / `bash` + 拦截执行 + round-2 回灌
- 路由映射：claude-opus-4-6 / claude-sonnet-4-5 / claude-haiku 等 Anthropic 模型 ID → MiniMax-M3
- 配置：YAML + 环境变量覆盖（`MINIMAX_API_KEY` / `MINIMAX_BASE_URL` 等）
- 端点：
  - `POST /v1/messages`（Anthropic Messages API 兼容）
  - `POST /v1/messages/count_tokens`
  - `GET /v1/health`
  - `GET /`（服务信息）
- 本地实现：
  - DuckDuckGo web_search（无需 key）
  - subprocess 代码执行沙箱（setrlimit 内存限制）
  - 可选 Serper / MiniMax MCP 后端
- 测试：21 个 pytest 用例（8 单元 + 13 E2E）+ GitHub Actions CI（Python 3.10/3.11/3.12 矩阵）
- 启动脚本：install.sh / start.sh / dev.sh
- 文档：README + docs/architecture.md（6 大块实现详解）
- 启动时配置校验：非 ASCII / 占位文本检测，给中文友好错误

### 🐛 修复 (Fixed)
- 修复 `pipeline` 直接 mutate payload 导致缓存 GET/PUT 键漂移的 bug
- 修复 `config.yaml` 默认 placeholder 含非 ASCII 时 httpx 启动崩溃的问题

### 🔒 安全 (Security)
- 启动时强制校验 `upstream.api_key` 必须是 ASCII
- 启动时拒绝占位符 key（`填您的` / `your-key-here`）
- `.gitignore` 屏蔽 `config.yaml`、本地 `~/.MiniMax-claude-proxy/` 等可能含 key 的文件

[Unreleased]: https://github.com/Mars535821089-ops/MiniMax-claude-proxy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Mars535821089-ops/MiniMax-claude-proxy/releases/tag/v0.1.0
