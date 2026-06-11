# 贡献指南

感谢您考虑为 MiniMax-Claude-Proxy 做出贡献！🎉
本项目欢迎任何形式的贡献：bug 报告、功能建议、文档改进、代码 PR。

---

## 🚀 快速开始

### 1. Fork + Clone

```bash
# Fork 本仓库到您的账号下（GitHub 网页操作）
# 然后 clone 您的 fork
git clone https://github.com/<your-username>/MiniMax-claude-proxy.git
cd MiniMax-claude-proxy
```

### 2. 配置开发环境

```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
pip install pytest pytest-asyncio ruff
```

### 3. 运行测试

```bash
pytest tests/ -v
```

应该看到 **21 passed**。

---

## 📐 项目结构

```
MiniMax-claude-proxy/
├── proxy/
│   ├── main.py              # FastAPI 入口 + pipeline 编排
│   ├── config.py            # YAML 配置 + Pydantic 校验
│   ├── models.py            # Anthropic Messages API 数据模型
│   ├── upstream.py          # MiniMax 异步客户端
│   ├── middleware/
│   │   ├── cache.py         # ① Prompt Caching
│   │   ├── thinking.py      # ② Extended Thinking
│   │   ├── schema.py        # ③ tool_use schema 简化
│   │   ├── multimodal.py    # ④ 多模态预处理
│   │   └── sse.py           # ⑤ SSE 稳定性
│   └── tools/               # ⑥ Server-side Tools
├── tests/                   # 21 个 pytest
├── scripts/                 # install / start / dev
├── docs/                    # 架构详解
├── config.yaml.example      # 配置模板
└── .github/                 # CI + Issue/PR 模板
```

---

## 🎯 我能贡献什么？

| 类型 | 难度 | 说明 |
|------|------|------|
| 🐛 修 bug | ⭐ | 从 [good first issue](https://github.com/Mars535821089-ops/MiniMax-claude-proxy/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) 选一个 |
| 📝 写文档 | ⭐ | 改 README / docstring / 翻译 |
| ✨ 加新中间件 | ⭐⭐⭐ | 在 `proxy/middleware/` 加一个文件 + 注册到 `main.py` |
| ✅ 补测试 | ⭐⭐ | 在 `tests/` 加用例 |
| ⚡ 性能优化 | ⭐⭐⭐ | 加 cache / 改并发模型 / 加监控 |

---

## 🔧 开发流程

### Step 1: 切分支

```bash
git checkout -b feat/your-feature
# 或
git checkout -b fix/your-bug
```

### Step 2: 写代码 + 测试

请确保：
- 新增的公共函数 / 类有 docstring
- 复杂逻辑加注释
- 给新功能写 pytest 用例（单元 + E2E）

### Step 3: 本地自检

```bash
# 跑全部测试
pytest tests/ -v

# 代码风格
ruff check proxy/ tests/

# 确认没把隐私 commit 进去
git diff --staged | grep -iE "api.?key|password|secret|token"  # 应为空
```

### Step 4: Commit

我们用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范：

```bash
git commit -m "feat: 加 Prometheus /metrics 端点"
git commit -m "fix: 修复并发请求下 cache key 漂移"
git commit -m "docs: 完善 README 排错章节"
git commit -m "test: 补 multimodal PDF 提取的 E2E"
git commit -m "refactor: 拆分 upstream.SSEStabilizer"
```

类型前缀：`feat` / `fix` / `docs` / `test` / `refactor` / `perf` / `chore` / `ci`

### Step 5: 推 + PR

```bash
git push origin feat/your-feature
```

然后在 GitHub 上从您的 fork 向本仓库的 `main` 发 PR，**请使用项目自带的 PR 模板**。

---

## 📋 中间件开发规范

如果您要加新中间件，请遵循以下约定（保持代码风格一致）：

```python
# proxy/middleware/your_middleware.py
from ..config import YourCfg
from ..utils.logging import get_logger

log = get_logger("your_middleware")


class YourMiddleware:
    def __init__(self, cfg: YourCfg):
        self.cfg = cfg

    def preprocess_request(self, payload: dict) -> dict:
        """请求前置处理：in-place 修改或返回新 dict。"""
        ...

    async def postprocess_response(self, response: dict) -> dict:
        """响应后置处理：异步可选。"""
        ...
```

然后在 `proxy/main.py` 的 `ProxyApp.__init__` 初始化、在 `pipeline()` 注册。
参考 `proxy/middleware/thinking.py` 是最标准的实现。

---

## 🧪 测试规范

- **单元测试**（`tests/test_basic.py`）：测纯函数 / 隔离逻辑，无 I/O
- **E2E 测试**（`tests/test_e2e.py`）：mock 上游 + 真代理 + httpx 客户端，覆盖 6 大块端到端

加新中间件时**必须**同时加 1 个单元 + 1 个 E2E 用例。

---

## 🤝 Code Review

所有 PR 都需要至少一次 review。Reviewer 会检查：
- 代码质量 / 可读性
- 是否有隐藏的安全 / 隐私风险
- 测试覆盖是否足够
- 文档是否同步更新

---

## ⚖️ 行为准则

- 尊重他人，多用欢迎用语
- 接受建设性批评
- 关注**对项目最有利**的事
- 严禁任何形式的骚扰

违反者将被永久禁言。

---

## 📮 联系方式

- 🐛 提 issue 优先
- 💬 一般讨论走 [GitHub Discussions](https://github.com/Mars535821089-ops/MiniMax-claude-proxy/discussions)
- 🔒 安全漏洞请看 [SECURITY.md](security.md)，**不要**公开提 issue

---

再次感谢您！🙏
