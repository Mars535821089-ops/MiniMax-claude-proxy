# 少数派草稿 — 教程向

**目标节点**：少数派 Matrix / 搞点副业
**配图位**：6 张（架构图、性能图、配置文件、终端输出、文档站首页、Star history）
**长度**：~2000 字
**风格**：手把手、有原理、有 FAQ、解决具体问题

---

## 标题

**《把 MiniMax-M3 跑进 Claude Code：本地代理搭建完全指南》**

副标题：一个 FastAPI 中间层，补齐 Anthropic 协议 6 大短板，让 Claude Code 在第三方模型上跑得跟原生一样稳。

---

## 正文

### 一、为什么要折腾这个？

[Claude Code](https://claude.com/claude-code) 客户端默认是为 Anthropic Claude 设计的，
依赖一批 Anthropic 独家的协议特性。

当你用 Claude Code 接入 [MiniMax-M3](https://platform.MiniMax.com/) 这种「Anthropic 兼容」接口时，会遇到：

- 🚫 **工具调用失败**：TodoWrite、Edit、Read 等工具的参数解析报错
- 🚫 **看不到 PDF**：图片/PDF 附件直接 415
- 🚫 **长任务被切断**：超过 30 秒的流式输出中途断开
- 🚫 **subagent 报错**：Plan 模式、Agent 模式频繁出错

**根因**：「Anthropic 兼容」≠「Anthropic 协议完整」。

### 二、解法

在 Claude Code 和 MiniMax-M3 之间塞一个**本地代理**，
把这些 Anthropic 独家特性**在本地重新实现**或**绕过**。

```
[Claude Code] → [MiniMax-Claude-Proxy] → [MiniMax-M3]
                        │
                        ├── SQLite prefix cache
                        ├── thinking shim
                        ├── schema shim ($ref/oneOf)
                        ├── multimodal shim
                        ├── SSE stabilizer
                        └── SSR tool hub
```

**对客户端完全透明** —— Claude Code 不知道中间有代理。

### 三、5 分钟上手

#### 1. 克隆并安装

```bash
git clone https://github.com/Mars535821089-ops/MiniMax-claude-proxy.git
cd MiniMax-claude-proxy
bash scripts/install.sh
```

`install.sh` 会做：
- 创建 `.venv` 虚拟环境
- 安装 14 个依赖（fastapi / uvicorn / httpx / pymupdf / tiktoken / ddgs 等）
- 拷贝 `config.yaml.example` → `config.yaml`
- 创建 `~/.MiniMax-claude-proxy/launch.sh` 启动器

#### 2. 配置 API Key

编辑 `config.yaml`：

```yaml
upstream:
  base_url: "https://api.minimaxi.com/anthropic"
  api_key: "sk-cp-填入您的真实key"  # 在 MiniMax 平台申请
  model_id: "MiniMax-M3"
```

🛡️ 启动时强制校验：API Key 必须是纯 ASCII，且不能是占位文本（防呆）。

#### 3. 启动代理

```bash
bash scripts/start.sh
# → INFO MiniMax-claude-proxy v0.1.1 listening on 127.0.0.1:8787
```

#### 4. 让 Claude Code 走代理

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8787
export ANTHROPIC_API_KEY=any-non-empty
export ANTHROPIC_MODEL=MiniMax-M3
claude
```

### 四、效果展示

#### 4.1 Prompt Caching 提速

**首次**请求：2.17s
**二次**同请求（命中 prefix 缓存）：**0.01s**

**217 倍提速** —— 不是营销话术，是 commit `9e9b5a6` 的真上游回归数据。

#### 4.2 6 大块全绿

昨天跑的真上游回归：

| # | 能力 | 表现 |
|---|------|------|
| ① | Prompt Caching | 217× 提速 ✅ |
| ② | Extended Thinking | thinking 块（英文推理 233 字）+ text 块双块输出 ✅ |
| ③ | 复杂 tool_use schema | oneOf 选对象分支嵌套还原 ✅ |
| ④ | 多模态 | 100×100 红 PNG 识别为「暗红色」✅ |
| ⑤ | SSE 稳定性 | 10 事件完整序列 + 15s ping + event_id 续传 ✅ |
| ⑥ | web_search | ddgs 端到端 PASS ✅ |

#### 4.3 测试覆盖

`pytest 21/21 PASS`（8 单元 + 13 E2E），CI 跑 3 Python 版本矩阵。

### 五、进阶配置

#### 5.1 缓存策略调优

```yaml
cache:
  enabled: true
  backend: sqlite
  strategy: prefix         # 严格匹配改 prefix，前缀命中也算
  default_ttl: 300         # 5 分钟
  long_ttl: 3600           # 长缓存 1 小时
  max_entries: 10000
```

#### 5.2 SSE 心跳（防长任务被切断）

```yaml
sse:
  buffer_tool_use_blocks: true   # 整块缓冲，避免 input_json_delta 错位
  inject_cache_usage_placeholder: true
```

`server.sse_ping_interval: 15` —— 15 秒一个心跳 ping，nginx 这类代理不会切断。

#### 5.3 关掉不需要的能力

```yaml
thinking:
  enabled: false          # 不需要 thinking 块时关掉，省 token
schema:
  enabled: true           # 必须开，否则 tool_use 出错
```

### 六、FAQ

**Q：会不会把我的 API Key 发到 MiniMax 之外？**
A：不会。所有流量只走「Claude Code → 本地代理 → MiniMax-M3」三段。
代理会校验 ASCII、占位文本、HTTP schema 三道防线。
gitleaks 在 CI 阶段也会扫历史 commit。

**Q：和直接配 Claude Code 的 OpenAI 兼容模式有什么区别？**
A：Claude Code 本身不支持「Anthropic 兼容」接口（这是 Anthropic 的护城河）。
本代理做的事就是**在协议层把 MiniMax-M3 包装成 Anthropic 协议**。

**Q：会拖慢 Claude Code 响应吗？**
A：会多一跳网络（~5ms 局域网），换来 6 大块功能全部可用。
Prompt Caching 命中时反而**快 217 倍**。

**Q：能跑在 Windows 上吗？**
A：能。`scripts/install.sh` 在 Git Bash / WSL 下均可。

**Q：生产环境怎么部署？**
A：v0.3.0 会出 Docker 镜像（GHCR 自动发布）。当前 v0.1.1 推荐本地 + systemd / launchd。

### 七、链接

- 仓库：https://github.com/Mars535821089-ops/MiniMax-claude-proxy
- 文档站：https://mars535821089-ops.github.io/MiniMax-claude-proxy/latest/
- 快速开始：https://mars535821089-ops.github.io/MiniMax-claude-proxy/latest/quickstart/
- 排错 FAQ：https://mars535821089-ops.github.io/MiniMax-claude-proxy/latest/troubleshooting/
- 真实数据来源：https://github.com/Mars535821089-ops/MiniMax-claude-proxy/blob/main/MILESTONES.md

### 八、写在最后

这是我第一次把完整项目放到 GitHub 开源。

如果你也踩过 Claude Code 跑在第三方模型上的坑，欢迎 Star ⭐ / 提 Issue / 提 PR。

如果觉得 217 倍提速看着心动 —— 自己 fork 一份跑跑看真上游。

打铁还需自身硬，无需扬鞭自奋蹄。🔨

---

## 配图位清单（投稿时补图）

1. **架构图**（必带，README mermaid 渲染图）
2. **性能对比**（必带，README 性能基线表格截图）
3. **配置文件示例**（config.yaml.example 高亮图）
4. **终端输出**（pytest 21/21 PASS）
5. **文档站首页**（mkdocs Material 主题）
6. **Star History**（star-history.com 自动生成）

---

> 备注：投稿前把 6 张配图实际生成，**少数派读者很挑配图质量**。
