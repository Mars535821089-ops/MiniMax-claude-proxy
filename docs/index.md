# MiniMax-Claude-Proxy

> 🔌 **在 Claude Code 框架下完整释放 MiniMax-M3 能力的本地代理**
>
> 补齐 6 大 Anthropic 协议短板，让第三方模型在 Claude Code 中跑得跟原生一样稳。

---

## 这是什么？

**MiniMax-Claude-Proxy** 是一个**本地代理**，嵌在 [Claude Code](https://claude.com/claude-code) 客户端和 [MiniMax-M3](https://platform.MiniMax.com/) 模型之间，
把 Anthropic 独有的 6 大协议特性**在本地重新实现或绕过**，对客户端保持完全透明。

5 分钟上手：[快速开始](quickstart.md) · 原理：[架构详解](architecture.md) · 排错：[FAQ](troubleshooting.md)

---

## 解决的 6 大块

| # | Anthropic 独有能力 | 没代理时的影响 | 本代理怎么做 |
|---|-------------------|--------------|------------|
| 1 | **Prompt Caching** (`cache_control`) | 长会话烧 token、Skill 反复重传 | SQLite 持久化前缀缓存 + cache_control 剥离 + 响应级 KV 缓存 + usage 占位回填 |
| 2 | **Extended Thinking** | Plan 模式 / 深度推理失效 | system 注入 `<thinking>` 引导 + 流式标签拆分回填为 thinking block |
| 3 | **复杂 tool_use schema** | TodoWrite/Edit 工具参数出错 | 递归展开 `$ref`、拍平 `oneOf/anyOf`、响应后还原嵌套 |
| 4 | **多模态** | 图/PDF 看不到 | 图片自动缩放、PDF→文本+关键页转图、URL→base64 拉取 |
| 5 | **长输出 SSE 稳定性** | 长任务被代理切断 | 15s 心跳 ping + tool_use 整块缓冲 + cache usage 占位注入 + event_id 续传 |
| 6 | **Server-side Tools** (web_search/code_execution/bash) | 工具不可用 | 本地实现 DuckDuckGo 搜索 + subprocess 沙箱 + 拦截 round-2 回灌 |

!!! tip "效果"
    实测：第一次请求 ~2.1s，相同请求二次命中缓存 **0.00s**，节省 99.9% 延迟。

---

## 为什么需要它？

Claude Code 默认依赖一批 Anthropic 独家协议特性（详见 [架构详解](architecture.md)）。
第三方"Anthropic 兼容"接口（包括 MiniMax-M3 的 `/anthropic` 端点）几乎都做不到完全对齐，
导致工具调用失败、PDF 看不到、长任务被切断、Subagent 出错报告。

**本项目让 Claude Code 跑在 MiniMax-M3 上，跟跑在 Claude Opus 上一样稳。**

---

## ✨ 特性一览

- 🚀 **0 配置文件改动** — Claude Code 切个 `ANTHROPIC_BASE_URL` 就完事
- 🔒 **零数据外传** — 所有流量都走您本地 + 您的上游 API，绝无第三方
- 🛡️ **隐私优先** — API Key 永不离开您机器，gitleaks 自动扫描防误提交
- 🧪 **21/21 测试通过** — 8 单元 + 13 E2E，三 Python 版本矩阵 CI
- 🌐 **跨平台** — macOS / Linux / Windows 均支持
- 📦 **零外部依赖**（除 `requirements.txt` 列出的 12 个 PyPI 包）

---

## 🏗️ 架构

```
┌─────────────────┐   /v1/messages    ┌──────────────────────────────────────────┐
│   Claude Code   │ ────────────────► │            MiniMax-Claude-Proxy           │
│ (Anthropic SDK) │                   │  ┌─model_mapping → cache_control_strip  │
└─────────────────┘                   │  ├─thinking.preprocess (注入system)     │
        ▲                              │  ├─schema.preprocess (拍平$ref/oneOf)   │
        │                              │  ├─ssr_tools.preprocess (翻译为普通工具) │
        │                              │  ├─multimodal.preprocess (图片PDF)      │
        │                              │  ├─cache.touch_prefix (注入usage占位)   │
        │                              │  ▼                                        │
        │                              │  upstream → MiniMax-M3 (Anthropic兼容API) │
        │                              │  ▼                                        │
        │                              │  ┌─thinking.stream_transformer (拆标签)  │
        │                              │  ├─sse.wrap (心跳+tool_use缓冲+占位)    │
        │                              │  ├─schema.postprocess (嵌套还原)        │
        │                              │  └─ssr_tools.execute (本地工具+回灌)    │
        │                              └──────────────────────────────────────────┘
        ▲                                                         │
        │                                              ┌──────────┴──────────┐
        │                                              ▼                     ▼
        │                                MiniMax /anthropic API      SQLite cache
        │
        └── SSE/JSON (对客户端完全透明) ◄─────────────────────────────┘
```

详见 [架构详解](architecture.md)。

---

## 🚀 5 分钟上手

=== "1. 安装"

    ```bash
    git clone https://github.com/Mars535821089-ops/MiniMax-claude-proxy.git
    cd MiniMax-claude-proxy
    bash scripts/install.sh
    ```

=== "2. 配置"

    编辑 `config.yaml`：

    ```yaml
    upstream:
      base_url: "https://api.minimaxi.com/anthropic"
      api_key: "sk-cp-YOUR-KEY-HERE"
      model_id: "MiniMax-M3"
    ```

=== "3. 启动"

    ```bash
    bash scripts/start.sh
    # → INFO MiniMax-claude-proxy v0.1.0 listening on 127.0.0.1:8787
    ```

=== "4. 走代理"

    ```bash
    export ANTHROPIC_BASE_URL=http://127.0.0.1:8787
    export ANTHROPIC_API_KEY=any-non-empty
    export ANTHROPIC_MODEL=MiniMax-M3
    claude
    ```

完整步骤见 [快速开始](quickstart.md)。

---

## 📚 文档导航

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **快速开始**

    ---

    5 分钟跑通代理 + 让 Claude Code 走代理

    [:octicons-arrow-right-24: 立即开始](quickstart.md)

-   :material-architecture:{ .lg .middle } **架构详解**

    ---

    6 大块中间件的设计权衡与数据流

    [:octicons-arrow-right-24: 深入了解](architecture.md)

-   :material-cog:{ .lg .middle } **配置参考**

    ---

    每个 config.yaml 字段的详细说明

    [:octicons-arrow-right-24: 查配置](configuration.md)

-   :material-api:{ .lg .middle } **API 端点**

    ---

    /v1/messages 等端点的完整规范

    [:octicons-arrow-right-24: 看 API](api.md)

-   :material-help-circle:{ .lg .middle } **排错 FAQ**

    ---

    常见问题与诊断方法

    [:octicons-arrow-right-24: 找答案](troubleshooting.md)

-   :material-github:{ .lg .middle } **贡献指南**

    ---

    如何为本项目贡献代码

    [:octicons-arrow-right-24: 参与](contributing.md)

</div>

---

## 🛡 隐私

本项目**不收集任何用户数据**。所有流量都走您的本地进程和您配置的上游 API。

- 日志仅记录在本地 stdout（不发送任何地方）
- SQLite 缓存文件位于 `~/.MiniMax-claude-proxy/cache.db`（您自己控制）
- API Key **绝不**会被代理转发到 MiniMax 之外的任何地方

详见 [安全政策](security.md)。

---

## 🌟 Star History

如果这个项目对您有帮助，欢迎给个 ⭐ 鼓励一下！

## 📄 License

[MIT](license.md) © 2026 The MiniMax-Claude-Proxy Authors

## 🙏 致谢

- [Anthropic](https://www.anthropic.com/) — Claude Code 客户端 + Messages API 协议
- [MiniMax](https://platform.MiniMax.com/) — MiniMax-M3 模型
- [FastAPI](https://fastapi.tiangolo.com/) / [httpx](https://www.python-httpx.org/) / [PyMuPDF](https://pymupdf.readthedocs.io/) / [DuckDuckGo](https://duckduckgo.com/) 等开源项目
