# 快速开始

5 分钟让 Claude Code 跑在 MiniMax-M3 上。

---

## 0. 前置要求

- **Python 3.10+**（推荐 3.12）
- **MiniMax-M3 API Key**（[申请地址](https://platform.MiniMax.com/)）
- 可选：`git` 用于克隆，`curl` 用于测试

---

## 1. 克隆 + 安装

```bash
git clone https://github.com/Mars535821089-ops/MiniMax-claude-proxy.git
cd MiniMax-claude-proxy
bash scripts/install.sh
```

`install.sh` 自动完成：

1. 创建 `.venv` 虚拟环境
2. 安装 `requirements.txt` 全部依赖
3. 拷贝 `config.yaml.example` → `config.yaml`
4. 创建 `~/.MiniMax-claude-proxy/launch.sh` 启动器

---

## 2. 配置 API Key

编辑 `config.yaml`：

```yaml
upstream:
  base_url: "https://api.minimaxi.com/anthropic"
  api_key: "sk-cp-填入您的真实key"   # ← 在此填入真实 key
  model_id: "MiniMax-M3"
```

!!! danger "关键检查"
    - `api_key` 必须是**纯 ASCII 字符**（以 `sk-cp-` 开头）
    - 不能是占位文本（`填您的` / `your-key-here`）
    - 启动时会自动校验，不通过会给出明确错误

---

## 3. 启动代理

```bash
bash scripts/start.sh
```

成功输出：

```
INFO    | __main__:lifespan - MiniMax-claude-proxy v0.1.0 listening on 127.0.0.1:8787
INFO    | __main__:lifespan - upstream → https://api.minimaxi.com/anthropic model=MiniMax-M3
INFO    | Uvicorn running on http://127.0.0.1:8787
```

---

## 4. 让 Claude Code 走代理

### 临时（关终端就失效）

=== "zsh (macOS 默认)"

    ```bash
    export ANTHROPIC_BASE_URL=http://127.0.0.1:8787
    export ANTHROPIC_API_KEY=any-non-empty
    export ANTHROPIC_MODEL=MiniMax-M3
    claude
    ```

=== "bash"

    ```bash
    export ANTHROPIC_BASE_URL=http://127.0.0.1:8787
    export ANTHROPIC_API_KEY=any-non-empty
    export ANTHROPIC_MODEL=MiniMax-M3
    claude
    ```

=== "PowerShell (Windows)"

    ```powershell
    $env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787"
    $env:ANTHROPIC_API_KEY = "any-non-empty"
    $env:ANTHROPIC_MODEL = "MiniMax-M3"
    claude
    ```

### 永久（写入 shell rc）

```bash
echo 'export ANTHROPIC_BASE_URL=http://127.0.0.1:8787' >> ~/.zshrc
echo 'export ANTHROPIC_API_KEY=any-non-empty' >> ~/.zshrc
echo 'export ANTHROPIC_MODEL=MiniMax-M3' >> ~/.zshrc
source ~/.zshrc
```

启动 `claude`，所有请求会经过代理，**6 大块功能自动激活**。

---

## 5. 验证

### 5.1 健康检查

```bash
curl http://127.0.0.1:8787/v1/health
```

预期输出：

```json
{"status":"ok","upstream":"https://api.minimaxi.com/anthropic"}
```

### 5.2 发个简单消息

```bash
curl -X POST http://127.0.0.1:8787/v1/messages \
  -H "x-api-key: any" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"MiniMax-M3","max_tokens":100,
       "messages":[{"role":"user","content":"你好"}]}'
```

预期返回 MiniMax-M3 的中文回答（`"usage.cache_read_input_tokens"` 字段应 > 0）。

### 5.3 在 Claude Code 中验证

启动 `claude` 后，问一个需要 thinking 的问题，例如：

> "用一句话介绍 Python 的 asyncio"

应能看到：

- 流畅的中文回答
- 流式输出时无工具调用错误
- `cache_creation_input_tokens` 首次为正，命中后为 0

---

## 下一步

- 🏗 [架构详解](architecture.md) — 了解 6 大块怎么实现的
- ⚙️ [配置参考](configuration.md) — 调优缓存、thinking 策略等
- 🔍 [排错 FAQ](troubleshooting.md) — 出问题先看这里
- 🤝 [贡献指南](contributing.md) — 想改点啥？
