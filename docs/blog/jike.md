# 即刻草稿 — 故事向

**目标节点**：即刻动态 / 圈子「AI 开发者」/「独立开发」
**配图位**：一张终端截图（pytest 21/21 PASS）+ 一张架构图
**长度**：~400 字
**风格**：个人故事、有点小激动、有梗

---

## 动态正文

昨天晚上我第一次在 GitHub 上传了一个完整可跑的项目，从 0 到 v0.1.1。

做的是个**本地代理**，解决一个我自己被折磨了很久的问题：Claude Code 默认只认 Anthropic 协议，
跑在 [MiniMax-M3](https://platform.MiniMax.com/) 这种「Anthropic 兼容」接口上时，
工具调用、PDF、长任务全废。

**做了什么**：在中间塞了一个 FastAPI 代理，把 6 大块协议特性在本地**重新实现或绕过**：
- 缓存层（SQLite prefix matching）
- thinking 模拟（system 注入 + 流式标签拆分）
- schema 拍平/还原（`$ref` / `oneOf`）
- 图片缩放 + PDF 拆页
- SSE 心跳 + tool_use 整块缓冲
- 本地工具集（用 `ddgs` 实现 web_search）

**最有成就感的瞬间**：

跑真上游回归测试那一秒 ——

```
① Prompt Caching     2.17s → 0.01s  (217× 提速)
② Extended Thinking  thinking 块 + text 块双块输出 ✅
③ 复杂 tool_use      oneOf 选对象分支嵌套还原 ✅
④ 多模态             100×100 红 PNG 识别为"暗红色" ✅
⑤ SSE 稳定性         10 事件 + 15s ping ✅
⑥ web_search         ddgs 端到端 PASS ✅
```

**6/6 大块全 PASS 那一刻，我从椅子上跳起来了。**

这是真的，不是营销话术 —— `git log` 里 commit `9e9b5a6` 留了完整数据。

---

**配图位 1**（必带）：pytest 21/21 PASS 终端输出（见 README）

**配图位 2**（可选）：架构图（mermaid 渲染）

---

**Link in bio**（如果有）：
- 仓库：github.com/Mars535821089-ops/MiniMax-claude-proxy
- 文档站：mars535821089-ops.github.io/MiniMax-claude-proxy/latest/

---

## 备用短版（即刻评论区用）

做了个 Claude Code 跑 MiniMax-M3 的本地代理，6 大块协议短板全补齐。
最有感的瞬间：真上游测试 6/6 大块全 PASS，二次请求 217 倍提速。
第一次开源，欢迎试用。
