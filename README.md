# MiniMax-Claude-Proxy

> 🔌 **在 Claude Code 框架下完整释放 MiniMax-M3 能力的本地代理**
>
> 补齐 6 大 Anthropic 协议短板，让第三方模型在 Claude Code 中跑得跟原生一样稳。

<p align="left">
  <a href="https://github.com/Mars535821089-ops/MiniMax-claude-proxy/blob/main/LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/Mars535821089-ops/MiniMax-claude-proxy?style=flat-square">
  </a>
  <a href="https://github.com/Mars535821089-ops/MiniMax-claude-proxy/releases">
    <img alt="Release" src="https://img.shields.io/github/v/release/Mars535821089-ops/MiniMax-claude-proxy?style=flat-square">
  </a>
  <a href="https://github.com/Mars535821089-ops/MiniMax-claude-proxy/actions">
    <img alt="CI" src="https://img.shields.io/github/actions/workflow/status/Mars535821089-ops/MiniMax-claude-proxy/test.yml?style=flat-square">
  </a>
  <a href="https://github.com/Mars535821089-ops/MiniMax-claude-proxy/stargazers">
    <img alt="Stars" src="https://img.shields.io/github/stars/Mars535821089-ops/MiniMax-claude-proxy?style=flat-square">
  </a>
  <a href="https://github.com/Mars535821089-ops/MiniMax-claude-proxy/issues">
    <img alt="Issues" src="https://img.shields.io/github/issues/Mars535821089-ops/MiniMax-claude-proxy?style=flat-square">
  </a>
  <a href="https://www.python.org/">
    <img alt="Python" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue?style=flat-square">
  </a>
  <a href="./MILESTONES.md">
    <img alt="Milestone" src="https://img.shields.io/badge/milestone-2026--06--12%20first%20release-ff69b4?style=flat-square">
  </a>
  <a href="https://mars535821089-ops.github.io/MiniMax-claude-proxy/latest/">
    <img alt="Docs" src="https://img.shields.io/badge/docs-mkdocs%20material-blue?style=flat-square&logo=materialformkdocs">
  </a>
  <a href="https://github.com/Mars535821089-ops/MiniMax-claude-proxy/actions/workflows/test.yml">
    <img alt="Tests" src="https://img.shields.io/badge/tests-21%2F21%20passing-brightgreen?style=flat-square">
  </a>
  <a href="https://github.com/Mars535821089-ops/MiniMax-claude-proxy/blob/main/MILESTONES.md#-2026-06-12--6-大块真上游全-pass">
    <img alt="E2E" src="https://img.shields.io/badge/e2e-6%2F6%20upstream%20PASS-success?style=flat-square">
  </a>
</p>

[🇺🇸 English](./README.en.md) | [🇨🇳 简体中文](./README.md)

> 📖 **完整文档已上线**：https://mars535821089-ops.github.io/MiniMax-claude-proxy/latest/ （mkdocs + Material 主题 + 中文搜索）

---

## 📑 目录

- [这是啥？](#-这是啥)
- [它解决什么](#-它解决什么)
- [架构](#-架构)
- [快速开始](#-快速开始)
- [配置](#-配置)
- [端点](#-端点)
- [开发与测试](#-开发与测试)
- [部署](#-部署)
- [排错 FAQ](#-排错-faq)
- [贡献](#-贡献)
- [License](#-license)

---

## 🤔 这是啥？

Claude Code 客户端默认是为 Anthropic Claude 设计的，依赖一批 Anthropic 独家的协议特性。
**MiniMax-M3** 通过"Anthropic 兼容"接口接进来时，这批特性多数不工作，导致：
工具调用失败、PDF 看不到、长任务被切断、subagent 出错报告。

**本项目是一个本地代理**，嵌在 Claude Code 和 MiniMax-M3 之间，把这些 Anthropic 特性
全部在本地**重新实现**或**绕过**掉，对客户端保持完全透明。

---

## 🎯 它解决什么

| # | Anthropic 独有能力 | 没代理时的影响 | 本代理怎么做 |
|---|-------------------|--------------|------------|
| ① | **Prompt Caching** (`cache_control`) | 长会话烧 token、Skill 反复重传 | SQLite 持久化前缀缓存 + cache_control 剥离 + 响应级 KV 缓存 + usage 占位回填 |
| ② | **Extended Thinking** | Plan 模式 / 深度推理失效 | system 注入 `<thinking>` 引导 + 流式标签拆分回填为 thinking block |
| ③ | **复杂 tool_use schema** | TodoWrite/Edit 工具参数出错 | 递归展开 `$ref`、拍平 `oneOf/anyOf`、响应后还原嵌套 |
| ④ | **多模态** | 图/PDF 看不到 | 图片自动缩放、PDF→文本+关键页转图、URL→base64 拉取 |
| ⑤ | **长输出 SSE 稳定性** | 长任务被代理切断 | 15s 心跳 ping + tool_use 整块缓冲 + cache usage 占位注入 + event_id 续传 |
| ⑥ | **Server-side Tools** (web_search/code_execution/bash) | 工具不可用 | 本地实现 DuckDuckGo 搜索 + subprocess 沙箱 + 拦截 round-2 回灌答案 |

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
        │                                                         │
        │                                              ┌──────────┴──────────┐
        │                                              ▼                     ▼
        │                                MiniMax /anthropic API      SQLite cache
        │                                                              (~/...cache.db)
        │
        └── SSE/JSON (对客户端完全透明) ◄─────────────────────────────┘
```

详见 [docs/architecture.md](./docs/architecture.md)。

---

## 🚀 快速开始

### 0. 前置要求

- **Python 3.10+**（推荐 3.12）
- **MiniMax-M3 API Key**（[申请地址](https://platform.MiniMax.com/)）
- 可选：`git` 用于克隆，`curl` 用于测试

### 1. 克隆 + 安装

```bash
git clone https://github.com/Mars535821089-ops/MiniMax-claude-proxy.git
cd MiniMax-claude-proxy
bash scripts/install.sh
```

`install.sh` 会做：
1. 创建 `.venv` 虚拟环境
2. 安装 `requirements.txt` 全部依赖
3. 拷贝 `config.yaml.example` → `config.yaml`
4. 创建 `~/.MiniMax-claude-proxy/launch.sh` 启动器

### 2. 配置

编辑 `config.yaml`：

```yaml
upstream:
  base_url: "https://api.minimaxi.com/anthropic"
  api_key: "sk-cp-填入您的真实key"
  model_id: "MiniMax-M3"
```

> 🛡️ `proxy` 启动时强制校验 API Key：必须是 ASCII，且不能是占位文本。

### 3. 启动

```bash
bash scripts/start.sh
# → INFO MiniMax-claude-proxy v0.1.0 listening on 127.0.0.1:8787
```

### 4. 让 Claude Code 走代理

临时（关终端就失效）：

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8787
export ANTHROPIC_API_KEY=any-non-empty
export ANTHROPIC_MODEL=MiniMax-M3
claude
```

永久（写入 `~/.zshrc` 或 `~/.bashrc`）：

```bash
echo 'export ANTHROPIC_BASE_URL=http://127.0.0.1:8787' >> ~/.zshrc
echo 'export ANTHROPIC_API_KEY=any-non-empty' >> ~/.zshrc
echo 'export ANTHROPIC_MODEL=MiniMax-M3' >> ~/.zshrc
source ~/.zshrc
```

启动 `claude`，所有请求会经过代理，**6 大块功能自动激活**。

### 5. 验证

```bash
# 健康检查
curl http://127.0.0.1:8787/v1/health

# 发个简单消息
curl -X POST http://127.0.0.1:8787/v1/messages \
  -H "x-api-key: any" -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"MiniMax-M3","max_tokens":100,
       "messages":[{"role":"user","content":"你好"}]}'
```

---

## ⚙️ 配置

`config.yaml` 全部配置项有中文注释。常用调优：

| 想做的事 | 怎么改 |
|---------|-------|
| 缓存命中更激进 | `cache.strategy: prefix` + 调大 `default_ttl` |
| 关掉 thinking 引导（节省 token） | `thinking.enabled: false` |
| 换搜索后端为 Serper | `server_side_tools.web_search.backend: serper` + `export SERPER_API_KEY=...` |
| 代码执行更宽松 | `server_side_tools.code_execution.timeout: 60` |
| PDF 只抽文本不转图 | `multimodal.pdf.strategy: text` |
| SSE 心跳更频繁 | `server.sse_ping_interval: 5` |
| 把 claude-opus-4-6 映射到不同 MiniMax 模型 | 编辑 `model_mapping` |

环境变量覆盖（无需改配置文件）：

| 变量 | 作用 |
|------|------|
| `MINIMAX_API_KEY` | 覆盖 `upstream.api_key` |
| `MINIMAX_BASE_URL` | 覆盖 `upstream.base_url` |
| `MINIMAX_PROXY_HOST` | 覆盖 `server.host` |
| `MINIMAX_PROXY_PORT` | 覆盖 `server.port` |
| `MINIMAX_PROXY_CONFIG` | 自定义 yaml 路径 |
| `SERPER_API_KEY` | web_search 选 serper 后端时需要 |

---

## 📡 端点

| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 服务信息 |
| `/v1/health` | GET | 详细健康检查 |
| `/v1/messages` | POST | **Anthropic Messages API 兼容主端点**（支持流式 + 非流式） |
| `/v1/messages/count_tokens` | POST | token 估算（避免 Claude Code 404） |

---

## 🧪 开发与测试

### 跑全部测试

```bash
source .venv/bin/activate
pip install pytest pytest-asyncio
pytest tests/ -v
```

应输出 **21 passed**（8 单元 + 13 E2E）。

### 开发模式（热重载）

```bash
bash scripts/dev.sh
```

### 单独跑某一类测试

```bash
# 单元
pytest tests/test_basic.py -v

# E2E（用 mock 上游，无需真 API Key）
pytest tests/test_e2e.py -v
```

### 测真实上游（需要 API Key）

```bash
# 1. 填好 config.yaml
# 2. 启动
bash scripts/start.sh
# 3. 发请求
curl -X POST http://127.0.0.1:8787/v1/messages \
  -H "x-api-key: any" -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"MiniMax-M3","max_tokens":100,
       "messages":[{"role":"user","content":"用一句话介绍 Python"}]}'
```

### 提交 PR

请看 [CONTRIBUTING.md](./CONTRIBUTING.md)。

---

## 🛠 部署

| 场景 | 推荐 |
|------|------|
| 个人 macOS + 临时用 | `nohup bash scripts/start.sh &` |
| 个人 macOS + 每天用 | launchd (见 [Wiki](https://github.com/Mars535821089-ops/MiniMax-claude-proxy/wiki)) |
| 多机 / 团队 | Docker (见 [Dockerfile](./Dockerfile)) |
| Linux 服务器 | systemd |

详细的 launchd / Docker / systemd 配置见 [docs/deploy.md](./docs/deploy.md)。

---

## 🔍 排错 FAQ

| 症状 | 排查 |
|------|------|
| 启动报 `upstream.api_key 含非 ASCII 字符` | 把 `config.yaml` 的 key 换成真 ASCII key（以 `sk-cp-` 开头） |
| Claude Code 报 401 | 检查 `ANTHROPIC_API_KEY` 是否非空（仅作占位，代理不校验） |
| 代理日志 `upstream 401` | 检查 `config.yaml` 的 `upstream.api_key` |
| 长任务卡住 | 把 `server.sse_ping_interval` 调小（默认 15s）|
| tool_use 参数错乱 | 把 `schema.flatten_oneof: false` 试试 |
| PDF 加载失败 | `pip install pymupdf` 验证；或改 `multimodal.pdf.strategy: text` |
| 缓存不命中 | 检查 sqlite：`sqlite3 ~/.MiniMax-claude-proxy/cache.db` 查行数 |
| 端口被占 | `lsof -i :8787` 找进程；改 `server.port` |

更多见 [docs/troubleshooting.md](./docs/troubleshooting.md)。

---

## 📊 性能基线

在 MacBook M1 + 本地 `127.0.0.1` 测试：

| 场景 | 首次 | 二次（命中缓存）|
|------|------|-----------------|
| 简单中文问答 | ~2.1s | **0.00s** |
| 流式输出 | 取决于上游 | 流式常驻 1 个心跳 ping |
| 100 KB 上传 | ~3.5s | 取决于上游 |

> 提示：本代理**不会让模型变快**，它只让协议层不拖后腿。

---

## 🤝 贡献

欢迎 PR / Issue / Discussion！请看 [CONTRIBUTING.md](./CONTRIBUTING.md)。

特别欢迎：
- 🐛 [Good first issues](https://github.com/Mars535821089-ops/MiniMax-claude-proxy/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
- 📝 翻译改进
- 🌐 新增 web_search / code_execution 后端

---

## 🛡 隐私

本项目**不收集任何用户数据**。所有流量都走您的本地进程和您配置的上游 API。

- 日志仅记录在本地 stdout（不发送任何地方）
- SQLite 缓存文件位于 `~/.MiniMax-claude-proxy/cache.db`（您自己控制）
- API Key **绝不**会被代理转发到 MiniMax 之外的任何地方

详见 [SECURITY.md](./SECURITY.md)。

---

## 🌟 Star History

如果这个项目对您有帮助，欢迎给个 ⭐ 鼓励一下！

<a href="https://star-history.com/#Mars535821089-ops/MiniMax-claude-proxy">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Mars535821089-ops/MiniMax-claude-proxy&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Mars535821089-ops/MiniMax-claude-proxy&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Mars535821089-ops/MiniMax-claude-proxy&type=Date" />
  </picture>
</a>

---

## 📄 License

[MIT](./LICENSE) © 2026 The MiniMax-Claude-Proxy Authors

---

## 🙏 致谢

- [Anthropic](https://www.anthropic.com/) - Claude Code 客户端 + Messages API 协议
- [MiniMax](https://platform.MiniMax.com/) - MiniMax-M3 模型
- [FastAPI](https://fastapi.tiangolo.com/) / [httpx](https://www.python-httpx.org/) / [PyMuPDF](https://pymupdf.readthedocs.io/) / [DuckDuckGo](https://duckduckgo.com/) 等开源项目

---

<p align="center">
  Made with ❤️ by the open-source community
</p>
