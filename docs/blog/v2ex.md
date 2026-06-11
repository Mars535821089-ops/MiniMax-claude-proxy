# V2EX 草稿 — 技术向

**目标节点**：`https://v2ex.com/write?tab=tech` （技术 tab）
**配图位**：README 架构图、性能对比 mermaid、pytest 终端输出
**长度**：~1000 字

---

## 标题（任选）

1. `做了一个本地代理，让 Claude Code 跑 MiniMax-M3 跟跑 Claude Opus 一样稳`
2. `在 Claude Code 框架下释放第三方模型：217 倍缓存提速是怎么来的`
3. `开源了一个 FastAPI 代理：补齐 Anthropic 协议 6 大短板`

---

## 正文

各位 V 友晚上好，分享一下我昨天刚在 GitHub 开源的一个小项目：
**[MiniMax-Claude-Proxy](https://github.com/Mars535821089-ops/MiniMax-claude-proxy)**。

### 背景

Claude Code 默认是为 Anthropic Claude 设计的，依赖一批 Anthropic 独家的协议特性：
- Prompt Caching（`cache_control` 块）
- Extended Thinking（流式 thinking 块）
- 复杂 `tool_use` schema（嵌套 `$ref` / `oneOf`）
- 多模态（图片 / PDF）
- 长输出 SSE 稳定性
- Server-side Tools（`web_search` / `code_execution`）

第三方「Anthropic 兼容」接口（包括 [MiniMax-M3](https://platform.MiniMax.com/)）做不到完全对齐，
导致 Claude Code 跑在 MiniMax-M3 上时：工具调用失败、PDF 看不到、长任务被切断、subagent 报错。

### 解决思路

本项目是一个**本地代理**，嵌在 Claude Code 和 MiniMax-M3 之间，把这些 Anthropic 特性
**在本地重新实现**或**绕过**，对客户端完全透明。

```
[Claude Code] -- HTTP/SSE --> [MiniMax-Claude-Proxy] -- HTTP --> [MiniMax-M3]
                                          │
                                          ├── SQLite prefix cache (217× 提速)
                                          ├── thinking shim (system 注入 + 标签拆分)
                                          ├── schema shim (拍平/还原)
                                          ├── multimodal shim (图片缩放/PDF 拆页)
                                          ├── SSE stabilizer (心跳+tool_use 整块缓冲)
                                          └── SSR tool hub (DuckDuckGo + subprocess)
```

### 效果

昨天用**真实 MiniMax-M3 API** 跑了 6 大块的端到端回归，**全部 PASS**：

| # | 大块 | 表现 |
|---|------|------|
| ① | Prompt Caching | 同请求 **2.17s → 0.01s（217× 提速）** |
| ② | Extended Thinking | thinking 块（英文推理 233 字）+ text 块双块输出 |
| ③ | 复杂 tool_use schema | oneOf 选对象分支，嵌套结构完全还原 |
| ④ | 多模态 | 100×100 红 PNG 识别为「暗红色」 |
| ⑤ | SSE 稳定性 | 10 事件完整序列 + 15s ping + event_id 续传 |
| ⑥ | web_search | ddgs 端到端 PASS（搜索 → 拦截 → 回灌） |

`pytest 21/21 PASS`（8 单元 + 13 E2E），CI 跑 3 Python 版本矩阵。

### 技术栈

- Python 3.10+ / FastAPI / uvicorn
- SQLite（aiosqlite）做 prefix cache
- loguru 做日志
- mkdocs Material 做文档站
- 14 个依赖，全在 `requirements.txt` 锁住

### 上手

```bash
git clone https://github.com/Mars535821089-ops/MiniMax-claude-proxy.git
cd MiniMax-claude-proxy
bash scripts/install.sh
# 编辑 config.yaml 填入你的 MiniMax API Key
bash scripts/start.sh
```

然后让 Claude Code 走代理：

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8787
export ANTHROPIC_API_KEY=any-non-empty
claude
```

### 隐私 / 安全

- API Key 永不离开本机（gitleaks 自动扫描 + ASCII 启动校验）
- 日志只写本地 stdout
- SQLite 缓存在 `~/.MiniMax-claude-proxy/cache.db`
- E2E 测试用 mock 上游，不污染真实流量

### 路线图

v0.2.0 — Web 控制台（实时看缓存命中率 / SSE 流）
v0.3.0 — Docker 镜像（一行 `docker run` 启动）
v1.0.0 — API 100% 兼容 Anthropic Messages spec

[GitHub 链接] [文档站] [Docker Hub（待）]

欢迎试用 / Star ⭐ / 提 Issue / PR。

---

> 备注：标题里「217 倍」是真实数据，不是营销话术。详见 commit `9e9b5a6` 的真上游回归。
