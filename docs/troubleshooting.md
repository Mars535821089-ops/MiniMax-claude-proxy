# 排错 FAQ

遇到问题先来这里。**80% 的问题 5 分钟内能解决**。

---

## 🚨 启动失败

### 启动报 `upstream.api_key 含非 ASCII 字符`

**症状**：

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
upstream
  Value error, upstream.api_key 含非 ASCII 字符。
```

**原因**：`config.yaml` 里的 api_key 是占位文本（含中文），不是真实 ASCII key。

**解决**：

1. 打开 `config.yaml`
2. 找到 `upstream.api_key: "sk-cp-..."`
3. 替换为真实 API Key（从 MiniMax 控制台复制，**以 `sk-cp-` 开头的纯 ASCII 字符串**）

### 启动报 `upstream.api_key 是占位文本`

**症状**：

```
Value error, upstream.api_key 是占位文本，请在 config.yaml 填入真实 API Key。
```

**解决**：同上。

### 启动报 UnicodeEncodeError / 'ascii' codec can't encode

**症状**：

```
UnicodeEncodeError: 'ascii' codec can't encode characters in position 6-13
```

**原因**：旧版本没有 ASCII 校验，配置文件含有非 ASCII 字符。

**解决**：升级到 v0.1.0+ 后会有友好错误；或直接用 ASCII 替换 `api_key`。

### 端口被占用

**症状**：

```
ERROR: [Errno 48] Address already in use
```

**解决**：

```bash
# 找出谁在占
lsof -i :8787

# 杀掉
kill -9 <PID>

# 或换个端口
echo "MINIMAX_PROXY_PORT=8788" >> .env
```

---

## 🌐 Claude Code 客户端问题

### Claude Code 报 401

**症状**：客户端显示 `401 Unauthorized`。

**排查**：

1. **检查 `ANTHROPIC_API_KEY` 是否非空**（代理不校验值，但 SDK 会校验有值）

    ```bash
    echo $ANTHROPIC_API_KEY    # 必须非空
    ```

2. **检查代理的 `config.yaml` 是否真 key**：

    ```bash
    grep "api_key" config.yaml   # 应是 sk-cp- 开头的真实字符串
    ```

3. **检查代理是否启动**：

    ```bash
    curl http://127.0.0.1:8787/v1/health
    ```

### Claude Code 报 Connection refused

**症状**：`Connection refused to 127.0.0.1:8787`。

**解决**：

- 代理没启动：`bash scripts/start.sh &`
- 端口不对：确认 `ANTHROPIC_BASE_URL` 与 `server.port` 一致

### Claude Code 报 tool_use.id 不匹配

**症状**：工具调用失败，错误含 `tool_use_id` 不匹配。

**原因**：上游 MiniMax-M3 兼容层对 `tool_use_id` 配对支持不稳。本代理已做 `tool_use` 整块缓冲。

**验证**：看代理日志，是否有 `[sqlite-cache HIT]` 或 `tool_use 缓冲`。若仍有问题，提 issue 并附日志。

### 长任务卡住 / 客户端无响应

**症状**：流式输出 60s 后断流，Claude Code 报错。

**原因**：上游 MiniMax 不发 SSE 心跳，被 nginx/Cloudflare 切断。

**解决**：本代理已注入 15s 心跳 ping。如仍卡住，调小：

```yaml
server:
  sse_ping_interval: 5    # 5 秒一次心跳
```

### 流式输出不完整

**症状**：回复在中间突然截断。

**解决**：

```yaml
server:
  request_timeout: 3600   # 调到 1 小时
sse:
  max_event_bytes: 131072 # 单事件字节加大
```

---

## 🧪 测试 / 工具问题

### Edit 工具老失败

**症状**：`Edit` 工具返回 "old_string not found"。

**原因**：模型在 `tool_use` 中 `old_string` 参数错位（schema 拍平导致）。

**解决**：

```yaml
schema:
  flatten_oneof: false   # 关闭 oneOf 拍平
  reconcile_response: true  # 确保开启
```

### TodoWrite 漏字段

**症状**：TodoWrite 调用缺字段。

**解决**：同 Edit 工具，关闭 schema 拍平试试。

### Web 搜索功能不能用

**症状**：模型说 "I cannot search"。

**排查**：

1. 确认 `server_side_tools.enable_web_search: true`
2. 确认上游 MiniMax-M3 已包含本地 `web_search` 工具定义
3. 查代理日志，是否有 `[ssr] intercepting server-side tools`

**换后端**：

```yaml
server_side_tools:
  web_search:
    backend: serper  # 或 MiniMax_mcp
```

```bash
export SERPER_API_KEY=your_serper_key
```

### 代码执行工具不能用

**症状**：模型说 "I cannot execute code"。

**排查**：

1. `server_side_tools.enable_code_execution: true`
2. Linux/macOS 上 `setrlimit` 生效；Windows 不生效但仍可跑
3. 查代理日志，看 `code_execution` 拦截日志

### PDF 加载失败

**症状**：附 PDF 文件，模型说 "I cannot read the file"。

**排查**：

```bash
# 验证 PyMuPDF 安装
python -c "import fitz; print(fitz.__version__)"
```

**解决**：

1. 重装 PyMuPDF：

    ```bash
    pip install -U pymupdf
    ```

2. 或改纯文本策略（不转图）：

    ```yaml
    multimodal:
      pdf:
        strategy: text
    ```

### 图片看不到

**症状**：附图片，模型说 "I cannot see the image"。

**排查**：

1. 图片 URL 是否可访问：`curl -I <url>`
2. 图片大小是否超限：

    ```yaml
    multimodal:
      image:
        max_size_mb: 20
    ```

3. 改大 `max_size_mb` 或关闭 `auto_resize`：

    ```yaml
    multimodal:
      image:
        auto_resize: false
    ```

---

## 💾 缓存问题

### 缓存不命中

**症状**：相同请求二次返回新结果。

**排查**：

```bash
# 查缓存文件
ls -la ~/.MiniMax-claude-proxy/cache.db

# 用 sqlite3 查行数
sqlite3 ~/.MiniMax-claude-proxy/cache.db "SELECT count(*) FROM response_cache;"

# 查代理日志
grep "cache HIT" ~/.MiniMax-claude-proxy/*.log
```

**可能原因**：

- 请求里 `metadata` 字段随机（如客户端时间戳）→ 调 cache 策略
- 缓存过期：调大 `cache.default_ttl`

### 缓存占用过大

**症状**：`~/.MiniMax-claude-proxy/cache.db` 涨到 GB 级。

**解决**：

```yaml
cache:
  max_entries: 1000    # 默认 10000，调小
```

或手动清空：

```bash
/bin/rm ~/.MiniMax-claude-proxy/cache.db
```

---

## 🔧 性能问题

### 第一次请求很慢

**原因**：路由 + 上游 MiniMax-M3 模型推理 + SQLite 写入。

**正常范围**：1.5-3s。第二次同请求应 < 100ms（命中缓存）。

### 流式输出不流畅

**症状**：流式有卡顿。

**排查**：

```bash
# 看 SSE 心跳
curl -N -X POST .../v1/messages ... -d '...stream=true...' | head -20
```

应看到 `event: ping` 每 15s 一次。

---

## 🐛 我还是没解决

1. **搜 [GitHub Issues](https://github.com/Mars535821089-ops/MiniMax-claude-proxy/issues)** 看看别人遇到过没
2. **开新 Issue**：
   - 用 [Bug 报告模板](https://github.com/Mars535821089-ops/MiniMax-claude-proxy/issues/new?template=bug.yml)
   - 附上**脱敏后**的代理日志
3. **去 [Discussions](https://github.com/Mars535821089-ops/MiniMax-claude-proxy/discussions)** 提问
