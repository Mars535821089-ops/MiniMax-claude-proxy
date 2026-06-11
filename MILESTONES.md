# 项目里程碑

记录 MiniMax-Claude-Proxy 走过的每一个关键时刻。
本文件由维护者用心维护，欢迎在 PR 中追加您的"我第一次用上 MiniMax-M3 + Claude Code"的日期。

---

## 🌟 2026-06-12 — 首次公开发布 v0.1.0

仓库 `MiniMax-claude-proxy` 在 GitHub 正式亮相。

**这一天发生了什么：**

- 📝 写下项目第一行代码 —— 解决 6 大块 Anthropic 协议短板
- ✅ 写完 **21 个 pytest**（8 单元 + 13 E2E），全绿
- 🔧 配置 **3 个 GitHub Actions workflow**（test / lint / gitleaks）
- 📚 写完 **5 个完整文档**（README / CHANGELOG / CONTRIBUTING / SECURITY / SUPPORT）
- 🛡️ 加 **gitleaks 密钥防护**（防止未来误提交 API Key）
- 🚀 发布 **v0.1.0 Release**，13 个 GitHub Topics
- 💬 启用 **GitHub Discussions**

**这一刻的关键词：**

> *第一次公开分享 / 第一个 v0.1.0 / 第一次跑通 21 个测试 / 第一次给 README 截图加徽章*

---

## 🎯 2026-06-12 — 6 大块真上游全 PASS

v0.1.1 真上游回归测试结果。每一块都用**真实 MiniMax-M3 API** 跑通端到端：

| # | 大块 | 真上游表现 |
|---|------|----------|
| ① | Prompt Caching | 同请求 2.17s → **0.01s**（**217 倍提速**）|
| ② | Extended Thinking | thinking 块（英文推理 233 字）+ text 块（中文解答）|
| ③ | 复杂 tool_use schema | oneOf 选对象分支，target={ipv4:"8.8.8.8", port:53} 嵌套还原 |
| ④ | 多模态 | 100×100 红 PNG 识别为"暗红色" |
| ⑤ | SSE 稳定性 | 10 事件完整序列 + 15s ping + event_id e1-e10 |
| ⑥ | web_search | ddgs 端到端 PASS（搜索 → 回灌 → 综合 "Python 3.13 于 2024 年 10 月 7 日正式发布"）|

修复路上踩到 1 个真生产 bug + 4 个 mkdocs CI bug，全部记录在 [CHANGELOG](CHANGELOG.md)。

---

## 🌐 2026-06-12 — GitHub Pages 文档站上线

[v0.4.0 — GitHub Pages 文档站](#) 提前达成 🎉

- 🌐 在线地址：https://mars535821089-ops.github.io/MiniMax-claude-proxy/latest/
- 🎨 mkdocs + Material 主题（中文优化）
- 🔍 全文搜索（中文友好，"缓存" "thinking" 都能搜到）
- 🌓 暗色模式 + 移动端响应式
- 🚀 push to main 自动部署 workflow
- 📚 11 个文档源文件：快速开始 / 架构详解 / 配置 / API / 排错 / 贡献 / 安全 / 协议 / 里程碑 / Changelog / 索引

---

## 🎯 未来里程碑（待实现，欢迎 PR）

| 目标 | 状态 | 描述 |
|------|------|------|
| v0.2.0 — Web 控制台 | 📋 计划 | 实时看缓存命中率 / SSE 事件流 / 工具调用日志 |
| v0.3.0 — Docker 镜像 | 📋 计划 | 一行 `docker run` 启动 |
| ~~v0.4.0 — GitHub Pages 文档站~~ | ✅ **DONE** | mkdocs material，已上线 |
| v1.0.0 — 生产稳定版 | 📋 计划 | API 100% 兼容 Anthropic Messages spec |
| 100 ⭐ | ⏳ 等待 | 第一次有用户 star |
| 第一个外部 PR | ⏳ 等待 | 来自其他贡献者的代码 |
| 第一次 Discussion | ⏳ 等待 | 来自社区的提问 |
| 第一次 Fork | ⏳ 等待 | 有人基于本项目改造 |

---

## 🙏 给未来维护者的一封信

如果你正在读这段文字，说明你正在接手一个有人认真打磨过的项目。

这个项目的代码不复杂 —— 一个 FastAPI 入口 + 5 个中间件 + 1 个本地工具集；
但每个决策都权衡过：哪些必须做、哪些不必要、哪些先 stub 后续再补。

请保持这些原则：

1. **隐私优先** —— 永远不要让用户的 API Key 离开他们的机器
2. **测试驱动** —— 任何中间件改动都加新测试
3. **文档先行** —— 用户痛点写进 README 的 FAQ
4. **小步迭代** —— 一个 PR 解决一个明确问题

谢谢你读到这里。

— 上一个维护者
