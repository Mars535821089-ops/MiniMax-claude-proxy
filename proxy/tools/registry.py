"""Server-side tools 注册中心 —— 拦截 Anthropic 内置工具，本地执行后塞回会话。

工作流：
1. preprocess: 扫描 tools 列表，识别 type 为 web_search_* / code_execution / bash_* 的项。
2. 把这些工具的 type 字段去掉，仅保留 name + 简短 input_schema，让 MiniMax-M3 当普通工具看待。
3. 当模型回 tool_use 且 name 命中时，proxy 拦截执行，把结果以 tool_result 形式 *本地拼接* 进下一轮。
4. 为减少协议复杂度，本版采用"单轮拦截 + 模型重答"模式：
   - 收到模型的 tool_use → 本地执行 → 把结果合成为 text，附在 assistant 消息后再发一次。
"""
from __future__ import annotations
from typing import Any
from ..config import ServerSideToolsCfg
from ..utils.logging import get_logger
from . import web_search as ws
from . import code_exec as ce

log = get_logger("ssr_tools")


# 工具命名映射（Anthropic 官方 type 前缀 → 本地实现）
_SERVER_SIDE_TYPES = {
    "web_search": "web_search",
    "web_search_20250305": "web_search",
    "code_execution": "code_execution",
    "code_execution_20250522": "code_execution",
    "bash_20250124": "bash",
    "text_editor_20250728": "text_editor",
}


class ServerSideToolsHub:
    def __init__(self, cfg: ServerSideToolsCfg):
        self.cfg = cfg

    def is_enabled(self, name: str) -> bool:
        if not self.cfg.enabled:
            return False
        return {
            "web_search": self.cfg.enable_web_search,
            "code_execution": self.cfg.enable_code_execution,
            "bash": self.cfg.enable_bash,
            "text_editor": False,
        }.get(name, False)

    def preprocess_request(self, payload: dict) -> tuple[dict, dict]:
        """把 server-side tools 翻译成普通 tool 定义。"""
        ctx: dict[str, str] = {}
        if not self.cfg.enabled:
            return payload, ctx
        tools = payload.get("tools")
        if not tools:
            return payload, ctx
        new_tools = []
        for t in tools:
            t_type = t.get("type")
            mapped = None
            if isinstance(t_type, str):
                for prefix, kind in _SERVER_SIDE_TYPES.items():
                    if t_type.startswith(prefix):
                        mapped = kind
                        break
            if mapped and self.is_enabled(mapped):
                name = t.get("name") or mapped
                ctx[name] = mapped
                tool_def = _BUILTIN_SCHEMAS[mapped].copy()
                tool_def["name"] = name
                new_tools.append(tool_def)
            elif mapped:
                # 启用了但功能关了 → 静默丢弃（避免 MiniMax-M3 报错）
                log.debug(f"drop server-side tool {t_type} (disabled)")
                continue
            else:
                new_tools.append(t)
        payload = {**payload, "tools": new_tools}
        return payload, ctx

    async def execute(self, name: str, kind: str, tool_input: dict) -> dict:
        """执行本地实现，返回 tool_result content。"""
        if kind == "web_search":
            query = tool_input.get("query") or tool_input.get("q") or ""
            results = await ws.web_search(query, cfg=self.cfg.web_search)
            return {"content": ws.format_results_as_text(results)}
        if kind == "code_execution":
            code = tool_input.get("code") or tool_input.get("source", "")
            lang = tool_input.get("language", "python")
            out = await ce.execute_code(code, cfg=self.cfg.code_execution, language=lang)
            text = f"exit_code: {out['exit_code']}\n--- stdout ---\n{out['stdout']}\n--- stderr ---\n{out['stderr']}"
            return {"content": text, "is_error": out["exit_code"] != 0}
        if kind == "bash":
            cmd = tool_input.get("command", "")
            out = await ce.execute_code(cmd, cfg=self.cfg.code_execution, language="bash")
            text = f"exit_code: {out['exit_code']}\n--- stdout ---\n{out['stdout']}\n--- stderr ---\n{out['stderr']}"
            return {"content": text, "is_error": out["exit_code"] != 0}
        return {"content": f"[unsupported server-side tool: {kind}]", "is_error": True}


_BUILTIN_SCHEMAS: dict[str, dict] = {
    "web_search": {
        "description": "在互联网搜索实时信息。返回标题、URL、摘要的列表。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        },
    },
    "code_execution": {
        "description": "在沙箱中执行 Python/Bash 代码并返回 stdout/stderr/exit_code。",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的源代码"},
                "language": {"type": "string", "enum": ["python", "bash"], "default": "python"},
            },
            "required": ["code"],
        },
    },
    "bash": {
        "description": "执行 bash 命令并返回输出。",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令"},
            },
            "required": ["command"],
        },
    },
}
