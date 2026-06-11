# 架构详解

本文档详述 6 大块功能各自的实现路径与权衡。

## ① Prompt Caching（`middleware/cache.py`）

### 问题
Claude Code 用 `cache_control: {type: "ephemeral"}` 标记 system / tools / 大块 user 消息，
Anthropic 后端按这些标记做 5 分钟 / 1 小时的 KV 缓存，复用率到 90% 都可能。
MiniMax-M3 兼容层不识别这个字段，直接报 400 或静默丢弃 → 每轮全量计费。

### 实现
三件事并行：

1. **`strip_cache_control(payload)`** — 递归 dict/list，删除所有 `cache_control` 字段。
2. **响应级 KV (SQLite)** — 以 `full_request_hash(剥离 cache_control 后)` 为 key 缓存上游响应。
   - 命中：直接返回，省一次上游调用。
   - 未命中：上游真跑 → 写回。
3. **前缀统计** — 以 `prefix_hash(system + tools + messages[:-1])` 记录"被见过的前缀"。
   - 命中前缀：注入 `cache_read_input_tokens = 估算 × 0.9` 到 `usage`。
   - 首次：注入 `cache_creation_input_tokens = 估算`。
   - 让 Claude Code 的统计 UI 看起来正常，避免它降级策略。

### 权衡
- 真实计算量没省，只是骗 UI；要真省必须在请求层去重（已做响应缓存）。
- SQLite 单文件，10k 条目以内查询 <5ms，足够。

---

## ② Extended Thinking（`middleware/thinking.py`）

### 问题
Anthropic 的 thinking block 是模型内置能力，MiniMax-M3 没有"signature thinking block"协议字段。

### 实现
1. **请求侧**：
   - 检测 `thinking: {type: "enabled"}` → 剥离。
   - 在 system prompt 追加中文引导："用 `<thinking></thinking>` 包裹推理"。
2. **响应侧（非流式）**：
   - 用正则把 text block 切成 `[text, thinking, text, ...]` 序列。
   - thinking block 加 `signature: "shim"` 标记是模拟的。
3. **响应侧（流式）**：
   - `_StreamThinkingSplitter` 维护滚动 buffer，避免标签跨 chunk。
   - 检测到 `<thinking>` → 后续 delta 输出 `type: "thinking_delta"`。
   - 检测到 `</thinking>` → 切回 `type: "text_delta"`。

### 权衡
- 不是真 thinking，质量看 MiniMax-M3 对引导的遵循度。
- 中文引导比英文有效（M3 中文偏好）。
- 流式拆分有 1-2 字符延迟（buffer 防切割）。

---

## ③ tool_use Schema 简化与还原（`middleware/schema.py`）

### 问题
Claude Code 的工具如 `TodoWrite`/`Edit` 用了：
- `$ref` 引用复用类型
- `oneOf`/`anyOf` 表达"X 或 Y"
- 嵌套 `properties` 深度 >3

第三方模型对这些支持差，要么报错要么返回的 `input` 结构错位。

### 实现
1. **请求侧**：
   - 深拷贝 `tools[*].input_schema`，存进 `ctx.tool_originals`。
   - 递归遍历：
     - `$ref` → 解析到根 `definitions/$defs` 替换为实际 schema。
     - `oneOf/anyOf` → 取第一个候选，其余写入 `description`。
     - 深度 > `max_depth` → 折成 `{type: "string"}` 占位。
2. **响应侧**：
   - 拿到 `tool_use.input` 后按原 schema 还原：
     - 期望 object 但拿到 string → JSON 解析。
     - 期望 array 但拿到 string → JSON 解析或包成单元素 list。
     - 递归处理嵌套 properties。

### 权衡
- `oneOf` 拍平丢信息（只用第一支）；用 description 兜底说明。
- 还原是尽力而为，模型回得太离谱救不回来。

---

## ④ 多模态预处理（`middleware/multimodal.py`）

### 问题
- 图片 URL → 第三方未必拉得动。
- PDF 第三方多半不支持。
- 音视频原生协议各家不同。

### 实现
- **image url** → httpx 拉取 → 转 base64。
- **image base64 过大** → PIL 缩放到长边 1568。
- **PDF**：
  - PyMuPDF 抽全文。
  - 页数 ≤ threshold 时把每页转 120dpi PNG 注入。
- **document URL** → 拉取 → 按 media_type 路由。
- **音视频**：默认占位文本；启用 `route_via_mcp` 时 POST 到 MiniMax MCP。

### 权衡
- PDF 太大只走文本，省 token；要看图自己调 `image_pages_threshold`。
- 图片缩放是有损（JPEG q=85）。

---

## ⑤ SSE 稳定性（`middleware/sse.py`）

### 问题
- Claude Code 的 SSE 消费器对协议细节敏感。
- 上游可能不发心跳 → nginx/Cloudflare 60s 切断。
- `input_json_delta` 跨多 chunk 时 Claude Code 经常解析失败。
- 上游不发 `cache_*_input_tokens` → Claude Code UI 显示异常。

### 实现
1. **心跳 ping**：每 `ping_interval` 秒（默认 15）输出 `: ping\n\n`。
2. **tool_use 缓冲**：
   - 检测 `content_block_start type=tool_use` → 不外发，存 buffer。
   - `input_json_delta` 累积 `partial_json`。
   - `content_block_stop` 时把累积的 JSON 解析成对象，重新发出**带完整 input 的** `content_block_start`，立刻跟一个 `content_block_stop`。
   - Claude Code 收到的就是一个完整原子化的 tool_use。
3. **usage 占位**：`message_start` 事件强制注入 cache_* 字段。
4. **event_id**：每个事件带递增 ID，支持 Last-Event-ID 续传。

### 权衡
- tool_use 缓冲会让 Claude Code "看不到打字进度"；换的是 100% 解析成功率。
- 心跳 15s 默认值适合大多数 CDN；nginx 默认 60s，留 4x 余量。

---

## ⑥ Server-side Tools（`tools/registry.py`）

### 实现
1. **翻译**：扫请求 tools，遇到 `type: "web_search_20250305"` 等 → 替换为 MiniMax-M3 看得懂的普通 tool 定义（name + input_schema）。
2. **拦截执行**：
   - 模型回 `tool_use name=web_search` → 本地 DuckDuckGo / MiniMax MCP / Serper 执行。
   - 把结果包成 `tool_result` 拼到 messages 后再调一次模型。
   - 模型生成最终答案返回。
3. **沙箱**：
   - subprocess + setrlimit 内存限制（仅 Unix）。
   - 临时目录隔离。
   - 超时强杀。

### 权衡
- 拦截 → round2 模式增加一次 RT；好处是协议简单、Claude Code 透明无感。
- 真生产用 code_execution 建议改 docker 后端。

---

## 数据流时序（流式 + tool）

```
client                proxy                              upstream
  │  POST /v1/messages   │                                  │
  │  (stream=true)       │                                  │
  │ ───────────────────► │                                  │
  │                      │ pipeline()                       │
  │                      │  - strip cache_control           │
  │                      │  - inject thinking guide         │
  │                      │  - simplify schemas              │
  │                      │  - translate ssr tools           │
  │                      │  - preprocess multimodal         │
  │                      │  - cache.touch_prefix            │
  │                      │ ────────────POST /v1/messages──► │
  │                      │                                  │ ...stream events
  │                      │ ◄────────────SSE────────────────│
  │                      │ stream_transformer(thinking)    │
  │                      │  - split <thinking> tags        │
  │                      │ sse.wrap()                      │
  │                      │  - heartbeat ping every 15s     │
  │                      │  - buffer tool_use blocks       │
  │                      │  - inject usage cache_*         │
  │ ◄────SSE chunks──────│                                  │
  │                      │                                  │
  │ (if ssr tool called) │                                  │
  │                      │ ssr_tools.execute(web_search)   │
  │                      │  - DuckDuckGo                    │
  │                      │ ────────POST round2 with result │
  │                      │ ◄────────final answer──────────│
  │ ◄────final SSE───────│                                  │
```
