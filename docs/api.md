# API 端点

本代理实现完整的 **Anthropic Messages API 兼容**接口，并补充了 Claude Code 必需的几个端点。

---

## 端点总览

| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 服务信息 |
| `/v1/health` | GET | 详细健康检查 |
| `/v1/messages` | POST | **Anthropic Messages API 兼容主端点** |
| `/v1/messages/count_tokens` | POST | token 估算（避免 Claude Code 404）|

---

## `GET /`

服务自描述。

**响应示例**：

```json
{
  "service": "MiniMax-claude-proxy",
  "version": "0.1.0",
  "status": "ok"
}
```

---

## `GET /v1/health`

**响应示例**：

```json
{
  "status": "ok",
  "upstream": "https://api.minimaxi.com/anthropic"
}
```

---

## `POST /v1/messages`

Anthropic Messages API 兼容主端点，支持非流式和流式两种模式。

### 请求头

```
x-api-key: any                  # Claude Code SDK 会校验有值即可
anthropic-version: 2023-06-01   # 必填
content-type: application/json
```

### 请求体

完整字段同 [Anthropic Messages API 规范](https://docs.anthropic.com/en/api/messages)，
本代理**额外支持**以下 Anthropic 字段（本地模拟实现）：

| 字段 | 处理 |
|------|------|
| `cache_control` | 递归剥离（避免上游 400）|
| `thinking` | 剥离 + 注入 system 引导 |
| `tools[].type=web_search_*` | 翻译为普通工具 |
| `tools[].type=code_execution_*` | 翻译为普通工具 |
| `tools[].type=bash_*` | 翻译为普通工具 |
| 复杂 `input_schema` (`$ref`/`oneOf`) | 拍平为简单 schema |

### 非流式响应

**请求示例**：

```bash
curl -X POST http://127.0.0.1:8787/v1/messages \
  -H "x-api-key: any" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "MiniMax-M3",
    "max_tokens": 200,
    "messages": [{"role":"user","content":"用一句话介绍 Python asyncio"}]
  }'
```

**响应示例**：

```json
{
  "id": "msg_067a2ab57a48e5b87e61840b73288ba7",
  "type": "message",
  "role": "assistant",
  "model": "MiniMax-M3",
  "content": [
    {
      "type": "text",
      "text": "Python 的 asyncio 是一个用于编写单线程并发代码的库..."
    }
  ],
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 131,
    "output_tokens": 24,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 114,
    "service_tier": "standard"
  }
}
```

!!! note "cache_*_input_tokens"
    本代理**强制注入**这两个字段。真实值由上游返回或基于前缀缓存统计估算。
    含义：
    - `cache_creation_input_tokens` — 本次新增的缓存条目 token 数
    - `cache_read_input_tokens` — 命中缓存的 token 数（> 0 表示有节省）

### 流式响应（SSE）

**请求示例**：

```bash
curl -N -X POST http://127.0.0.1:8787/v1/messages \
  -H "x-api-key: any" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "MiniMax-M3",
    "max_tokens": 100,
    "stream": true,
    "messages": [{"role":"user","content":"用一句话说 quicksort"}]
  }'
```

**响应（Server-Sent Events）**：

```
id: e1
event: message_start
data: {"type":"message_start","message":{"id":"msg_...","model":"MiniMax-M3",...}}

id: e2
event: ping
data: {"type":"ping"}

id: e3
event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

id: e4
event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"选取"}}

id: e5
event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"一个基准元素..."}}

id: e6
event: content_block_stop
data: {"type":"content_block_stop","index":0}

id: e7
event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":22}}

id: e8
event: message_stop
data: {"type":"message_stop"}
```

!!! tip "SSE 事件 ID 续传"
    每个事件带递增 `id: e1, e2, ...`。
    客户端断流后可发 `Last-Event-ID` 头（虽然本代理暂未实现断点续传，但事件 ID 仍可用于客户端去重）。

#### 工具调用流式

`tool_use` 块在本代理中被**整块缓冲**后再发出，确保 Claude Code 收到的是完整原子化的 input：

```
id: e5
event: content_block_start
data: {"type":"content_block_start","index":0,
       "content_block":{"type":"tool_use","id":"tu_1","name":"calc",
                        "input":{"x":42}}}

id: e6
event: content_block_stop
data: {"type":"content_block_stop","index":0}
```

不会有 `input_json_delta` 分散事件，因为本代理把上游多个 `partial_json` 合并后再发。

---

## `POST /v1/messages/count_tokens`

Anthropic SDK 会调用此端点估算 token 数。本代理实现经验估算（每 3 字符约 1 token）。

**请求示例**：

```bash
curl -X POST http://127.0.0.1:8787/v1/messages/count_tokens \
  -H "content-type: application/json" \
  -d '{"messages":[{"role":"user","content":"hello world"}]}'
```

**响应示例**：

```json
{
  "input_tokens": 4
}
```

!!! warning "估算精度"
    本端点是**经验估算**（约 1 token / 3 字符），并非精确计费。
    Claude Code 主要用它判断是否需要触发缓存压缩，对精度不敏感。

---

## 错误响应

代理透传上游错误（4xx 不重试），并在 500 时给出内部错误。

**示例**（上游 401）：

```json
{
  "type": "error",
  "error": {
    "type": "upstream_error",
    "message": "401: {\"error\":{\"type\":\"...\",\"message\":\"invalid api key\"}}"
  }
}
```

**示例**（本地 500）：

```json
{
  "type": "error",
  "error": {
    "type": "internal_error",
    "message": "具体错误堆栈"
  }
}
```

---

## 端到端示例

### Python (Anthropic SDK)

```python
import os
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:8787"
os.environ["ANTHROPIC_API_KEY"] = "any"
os.environ["ANTHROPIC_MODEL"] = "MiniMax-M3"

import anthropic
client = anthropic.Anthropic()
msg = client.messages.create(
    model="MiniMax-M3",
    max_tokens=200,
    messages=[{"role": "user", "content": "你好"}]
)
print(msg.content[0].text)
```

### Claude Code CLI

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8787
export ANTHROPIC_API_KEY=any-non-empty
export ANTHROPIC_MODEL=MiniMax-M3
claude
```

### TypeScript (Anthropic SDK)

```typescript
import Anthropic from "@anthropic-ai/sdk";
const client = new Anthropic({
  apiKey: "any",
  baseURL: "http://127.0.0.1:8787",
});
const msg = await client.messages.create({
  model: "MiniMax-M3",
  max_tokens: 200,
  messages: [{ role: "user", content: "Hello" }],
});
console.log(msg.content[0].text);
```
