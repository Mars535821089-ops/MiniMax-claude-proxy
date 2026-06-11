# Security Policy

## 支持的版本

| 版本 | 支持 |
|------|------|
| 0.1.x (最新) | ✅ |
| < 0.1.0 | ❌ |

## 报告漏洞

**⚠️ 请勿在公开 issue 报告安全漏洞。**

请发邮件到项目维护者（见 [GitHub Profile](https://github.com/Mars535821089-ops)），并在标题前加 `[SECURITY]`。

请包含：
- 漏洞描述
- 复现步骤
- 影响范围
- 您的联系方式

我们承诺：
- **48 小时内**响应
- 评估后**7 天内**给出修复时间表
- 修复后给您 credit（除非您要求匿名）

## 我们会怎么处理

1. 确认漏洞
2. 评估严重性（critical / high / medium / low）
3. 内部修复
4. 发安全补丁 release
5. 在 CHANGELOG / GitHub Security Advisories 致谢

## 安全最佳实践（用户侧）

为保护您的 API Key：

1. **永远不要**把 `config.yaml` 提交到 git（已被 `.gitignore` 屏蔽）
2. **不要**在 issue / PR / 公开聊天里贴真实 key
3. 用 **环境变量** 临时覆盖（`MINIMAX_API_KEY`）比改文件更安全
4. 定期**轮换** 您的 API Key
5. 代理监听 `127.0.0.1`（不是 `0.0.0.0`），仅本机可访问，**不要** 改成 0.0.0.0 暴露在公网
6. 配合 **MiniMax 账户的 IP 白名单** 进一步收紧

## 已知安全考虑

- **code_execution 沙箱**：默认是 `subprocess + setrlimit`，隔离性弱。
  攻击场景：模型被诱导跑恶意代码。本地个人用问题不大，多用户场景建议改 `docker` 后端（已留接口位）。
- **code_execution 内存限制**：依赖 Unix setrlimit，**Windows 不生效**。
- **配置文件含明文 Key**：加密的方案（KMS / HashiCorp Vault）暂未支持。
