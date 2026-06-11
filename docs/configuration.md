# 配置参考

`config.yaml` 全部配置项详解。所有项都有默认值，最小配置只须填 `upstream.api_key`。

---

## 完整示例

```yaml
server:
  host: 127.0.0.1
  port: 8787
  log_level: INFO
  sse_ping_interval: 15
  request_timeout: 1800

upstream:
  base_url: "https://api.minimaxi.com/anthropic"
  api_key: "sk-cp-YOUR-KEY-HERE"
  model_id: "MiniMax-M3"
  max_connections: 32
  max_retries: 3
  retry_backoff_seconds: 2

cache:
  enabled: true
  backend: sqlite
  db_path: ~/.MiniMax-claude-proxy/cache.db
  strategy: prefix
  default_ttl: 300
  long_ttl: 3600
  max_entries: 10000

thinking:
  enabled: true
  injection: system_prompt
  open_tag: "<thinking>"
  close_tag: "</thinking>"
  default_budget: 8192

server_side_tools:
  enabled: true
  enable_web_search: true
  enable_code_execution: true
  enable_bash: false
  web_search:
    backend: duckduckgo
    max_results: 5
    timeout: 10
  code_execution:
    backend: subprocess
    timeout: 30
    memory_limit_mb: 512

schema:
  enabled: true
  flatten_oneof: true
  flatten_anyof: true
  expand_refs: true
  max_depth: 5
  reconcile_response: true

multimodal:
  enabled: true
  image:
    max_size_mb: 20
    auto_resize: true
    target_long_edge: 1568
  pdf:
    strategy: text_and_images
    max_pages: 50
    image_pages_threshold: 5
  audio_video:
    route_via_mcp: true
    mcp_endpoint: "http://127.0.0.1:8765"

sse:
  buffer_tool_use_blocks: true
  max_event_bytes: 65536
  reconnect_window: 60
  inject_cache_usage_placeholder: true

model_mapping:
  "claude-opus-4-6": "MiniMax-M3"
  "claude-opus-4-1-20250805": "MiniMax-M3"
  "claude-sonnet-4-5": "MiniMax-M3"
  "claude-3-5-haiku-20241022": "MiniMax-M3"
  "claude-3-5-sonnet-20241022": "MiniMax-M3"
  "_default": "MiniMax-M3"
```

---

## 字段说明

### `server`

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `host` | str | `127.0.0.1` | 监听地址。**不要改成 `0.0.0.0`**，会暴露在公网 |
| `port` | int | `8787` | 监听端口 |
| `log_level` | str | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `log_file` | str | None | 日志文件路径（None = 仅 stderr）|
| `sse_ping_interval` | int | `15` | SSE 心跳间隔（秒），防长任务被代理切断 |
| `request_timeout` | int | `1800` | 单次请求最大执行时间（秒）|

### `upstream`

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `base_url` | str | **必填** | 上游 API 地址（Anthropic 兼容）|
| `api_key` | str | **必填** | 上游 API Key（启动时校验 ASCII）|
| `model_id` | str | `MiniMax-M3` | 实际调用的上游模型 ID |
| `max_connections` | int | `32` | httpx 连接池大小 |
| `max_retries` | int | `3` | 上游失败重试次数 |
| `retry_backoff_seconds` | float | `2.0` | 重试退避基数（指数退避）|

### `cache` — Prompt Caching

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enabled` | bool | `true` | 总开关 |
| `backend` | str | `sqlite` | 存储后端：`sqlite` / `memory` |
| `db_path` | str | `~/.MiniMax-claude-proxy/cache.db` | SQLite 数据库路径 |
| `strategy` | str | `prefix` | 命中策略：`prefix` / `strict` |
| `default_ttl` | int | `300` | 响应级缓存 TTL（秒）|
| `long_ttl` | int | `3600` | 前缀缓存 TTL（秒）|
| `max_entries` | int | `10000` | 最大缓存条目（LRU 触发时清理 1/4）|

!!! tip "调优建议"
    - 想更激进：调大 `default_ttl`（如 1800）
    - 想更省磁盘：调小 `max_entries`（如 1000）
    - 内存测试用：改 `backend: memory`

### `thinking` — Extended Thinking

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enabled` | bool | `true` | 总开关 |
| `injection` | str | `system_prompt` | 引导注入位置：`system_prompt` / `user_prefix` |
| `open_tag` | str | `<thinking>` | 引导用的开标签 |
| `close_tag` | str | `</thinking>` | 引导用的闭标签 |
| `default_budget` | int | `8192` | thinking 预算上限（token 数）|

!!! tip "调优建议"
    - 想让响应更简洁：设 `enabled: false`
    - 想让模型思考更多：调大 `default_budget`（如 16384）

### `server_side_tools` — 本地实现的 Anthropic 工具

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enabled` | bool | `true` | 总开关 |
| `enable_web_search` | bool | `true` | 启用 web_search 本地实现 |
| `enable_code_execution` | bool | `true` | 启用 code_execution 本地实现 |
| `enable_bash` | bool | `false` | 启用 bash 本地实现（Claude Code 已有内置 Bash）|

#### `web_search`

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `backend` | str | `duckduckgo` | 后端：`duckduckgo` / `MiniMax_mcp` / `serper` |
| `max_results` | int | `5` | 单次返回最大结果数 |
| `timeout` | int | `10` | 单次搜索超时（秒）|

后端说明：

- **duckduckgo**：免费、无 key；适合默认
- **MiniMax_mcp**：通过 `http://127.0.0.1:8765` 走 MiniMax MCP server
- **serper**：需要 `SERPER_API_KEY` 环境变量

#### `code_execution`

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `backend` | str | `subprocess` | 后端：`subprocess` / `docker` |
| `timeout` | int | `30` | 单次执行超时（秒）|
| `memory_limit_mb` | int | `512` | 内存限制（MB，**Windows 不生效**）|

### `schema` — tool_use schema 处理

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enabled` | bool | `true` | 总开关 |
| `flatten_oneof` | bool | `true` | 拍平 oneOf 字段 |
| `flatten_anyof` | bool | `true` | 拍平 anyOf 字段 |
| `expand_refs` | bool | `true` | 展开 $ref 引用 |
| `max_depth` | int | `5` | 最大递归深度 |
| `reconcile_response` | bool | `true` | 响应后还原嵌套结构 |

### `multimodal` — 多模态预处理

#### `image`

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_size_mb` | int | `20` | 单张图最大体积 |
| `auto_resize` | bool | `true` | 自动缩放（长边 > target 时）|
| `target_long_edge` | int | `1568` | 缩放目标长边（px）|

#### `pdf`

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `strategy` | str | `text_and_images` | 提取策略：`text` / `text_and_images` / `images_only` |
| `max_pages` | int | `50` | 最大处理页数 |
| `image_pages_threshold` | int | `5` | 超过此页数时只抽文本不转图 |

#### `audio_video`

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `route_via_mcp` | bool | `true` | 路由到 MiniMax MCP |
| `mcp_endpoint` | str | `http://127.0.0.1:8765` | MCP server 地址 |

### `sse` — SSE 稳定性

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `buffer_tool_use_blocks` | bool | `true` | 缓冲 `tool_use` 整块再发 |
| `max_event_bytes` | int | `65536` | 单 SSE 事件最大字节 |
| `reconnect_window` | int | `60` | 客户端断流后重连窗口（秒）|
| `inject_cache_usage_placeholder` | bool | `true` | 注入 `cache_*_input_tokens` 占位 |

### `model_mapping` — 模型 ID 重映射

把 Claude Code 发送的模型 ID 映射到上游实际模型。`_default` 是兜底。

---

## 环境变量覆盖

无需改文件即可临时调整：

| 变量 | 覆盖字段 |
|------|---------|
| `MINIMAX_API_KEY` | `upstream.api_key` |
| `MINIMAX_BASE_URL` | `upstream.base_url` |
| `MINIMAX_PROXY_HOST` | `server.host` |
| `MINIMAX_PROXY_PORT` | `server.port` |
| `MINIMAX_PROXY_CONFIG` | yaml 文件路径 |
| `SERPER_API_KEY` | web_search backend=serper 时需要 |
| `MINIMAX_MCP_HTTP` | web_search backend=MiniMax_mcp 时的 endpoint |

---

## 常见调优场景

| 想做的事 | 怎么改 |
|---------|-------|
| 缓存命中更激进 | `cache.strategy: prefix` + 调大 `default_ttl` |
| 关掉 thinking 引导 | `thinking.enabled: false` |
| 换搜索后端为 Serper | `server_side_tools.web_search.backend: serper` + `export SERPER_API_KEY=...` |
| 代码执行更宽松 | `server_side_tools.code_execution.timeout: 60` |
| PDF 只抽文本 | `multimodal.pdf.strategy: text` |
| SSE 心跳更频繁 | `server.sse_ping_interval: 5` |
| 调大 thinking 预算 | `thinking.default_budget: 16384` |
| 用 docker 沙箱 | `server_side_tools.code_execution.backend: docker` |
