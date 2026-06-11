"""中间件 #2: Extended Thinking 模拟。

策略：
1. 检测请求 `thinking: {type: "enabled", budget_tokens: N}`，从请求中移除（MiniMax 不识别）。
2. 在 system prompt 末尾追加一段引导：让模型用 `<thinking></thinking>` 包裹推理。
3. 流式响应中解析 `<thinking>` 标签，转换成 Anthropic 的 thinking content block 事件。
4. 模型如果原生支持 thinking（MiniMax-M3 有自己的推理），保留之；如果没有，靠 prompt 引导。
"""
from __future__ import annotations
import re
from typing import Any
from ..config import ThinkingCfg
from ..utils.logging import get_logger

log = get_logger("thinking")


_THINK_GUIDE_ZH = """\

[推理模式 - 重要]
在给出最终答案之前，请用 <thinking></thinking> 标签包裹您的内部推理过程。
- 推理过程：分析问题、考虑多种方案、评估权衡。
- 思考预算上限约 {budget} tokens。
- thinking 块结束后再输出正式回复。
- 如调用工具，先在 thinking 中说明意图，再发出 tool_use。
"""


class ThinkingShim:
    """Thinking 模拟层。"""

    def __init__(self, cfg: ThinkingCfg):
        self.cfg = cfg
        self._open = cfg.open_tag
        self._close = cfg.close_tag
        self._open_re = re.compile(re.escape(self._open), re.IGNORECASE)
        self._close_re = re.compile(re.escape(self._close), re.IGNORECASE)

    def preprocess_request(self, payload: dict) -> tuple[dict, dict]:
        """从请求剥离 thinking 字段并在 system 注入引导。返回 (new_payload, context)。

        context 用于流式处理时知道是否要做 thinking-block 包装。
        """
        ctx = {"enabled": False, "budget": self.cfg.default_budget}
        thinking_cfg = payload.get("thinking")
        if not self.cfg.enabled or not isinstance(thinking_cfg, dict):
            # 即使配置开了但请求没要求，也不主动注入
            return payload, ctx
        if thinking_cfg.get("type") != "enabled":
            return _drop_key(payload, "thinking"), ctx

        ctx["enabled"] = True
        ctx["budget"] = int(thinking_cfg.get("budget_tokens", self.cfg.default_budget))
        payload = _drop_key(payload, "thinking")

        guide = _THINK_GUIDE_ZH.format(budget=ctx["budget"])
        payload = self._inject_into_system(payload, guide)
        log.debug(f"thinking enabled, budget={ctx['budget']}")
        return payload, ctx

    def _inject_into_system(self, payload: dict, text: str) -> dict:
        system = payload.get("system")
        if system is None:
            payload["system"] = text.lstrip()
        elif isinstance(system, str):
            payload["system"] = system + "\n" + text
        elif isinstance(system, list):
            # Anthropic system 也可以是 [{type:"text", text:"..."}]
            payload["system"] = [*system, {"type": "text", "text": text.lstrip()}]
        return payload

    # === 非流式响应：把 <thinking> 文本块切出为 thinking content block ===
    def postprocess_response(self, response: dict, ctx: dict) -> dict:
        if not ctx.get("enabled"):
            return response
        new_content: list[dict] = []
        for block in response.get("content", []):
            if block.get("type") != "text":
                new_content.append(block)
                continue
            text = block.get("text", "")
            new_content.extend(self._split_text_block(text))
        response["content"] = new_content
        return response

    def _split_text_block(self, text: str) -> list[dict]:
        """把含 <thinking> 的文本拆成 [thinking, text, thinking, text, ...] 序列。"""
        out: list[dict] = []
        pos = 0
        while pos < len(text):
            m_open = self._open_re.search(text, pos)
            if not m_open:
                tail = text[pos:]
                if tail.strip():
                    out.append({"type": "text", "text": tail})
                break
            if m_open.start() > pos:
                head = text[pos:m_open.start()]
                if head.strip():
                    out.append({"type": "text", "text": head})
            m_close = self._close_re.search(text, m_open.end())
            if not m_close:
                # 未闭合：视为 thinking 全收尾
                out.append({"type": "thinking", "thinking": text[m_open.end():], "signature": "shim"})
                break
            out.append({
                "type": "thinking",
                "thinking": text[m_open.end():m_close.start()].strip(),
                "signature": "shim",
            })
            pos = m_close.end()
        return out or [{"type": "text", "text": text}]

    # === 流式：返回一个流转换器 ===
    def stream_transformer(self, ctx: dict):
        if not ctx.get("enabled"):
            return _passthrough
        return _StreamThinkingSplitter(self._open, self._close)


def _drop_key(payload: dict, key: str) -> dict:
    return {k: v for k, v in payload.items() if k != key}


async def _passthrough(events):
    async for ev in events:
        yield ev


class _StreamThinkingSplitter:
    """把流中 content_block_delta 的 text 增量按 <thinking> 切分为 thinking_delta + text_delta。

    实现要点：
    - 用一个滚动 buffer，避免标签跨 chunk 时切断。
    - 维护当前是否在 thinking 状态。
    - 在标签边界处插入 content_block_stop / content_block_start。
    """

    def __init__(self, open_tag: str, close_tag: str):
        self.open_tag = open_tag
        self.close_tag = close_tag

    async def __call__(self, events):
        in_thinking = False
        buffer = ""
        # 当前 thinking/text content_block 索引（用于事件 index）
        current_idx: int | None = None
        async for ev in events:
            name = ev.get("event")
            data = ev.get("data", {})
            if name != "content_block_delta":
                yield ev
                continue
            delta = data.get("delta", {})
            if delta.get("type") != "text_delta":
                yield ev
                continue
            text = delta.get("text", "")
            buffer += text
            out_text = ""
            out_thinking = ""
            # 处理 buffer
            while buffer:
                if in_thinking:
                    idx = buffer.find(self.close_tag)
                    if idx == -1:
                        # 保留一点尾巴防止标签被切
                        keep = len(self.close_tag) - 1
                        if len(buffer) > keep:
                            out_thinking += buffer[:-keep]
                            buffer = buffer[-keep:]
                        break
                    out_thinking += buffer[:idx]
                    buffer = buffer[idx + len(self.close_tag):]
                    in_thinking = False
                else:
                    idx = buffer.find(self.open_tag)
                    if idx == -1:
                        keep = len(self.open_tag) - 1
                        if len(buffer) > keep:
                            out_text += buffer[:-keep]
                            buffer = buffer[-keep:]
                        break
                    out_text += buffer[:idx]
                    buffer = buffer[idx + len(self.open_tag):]
                    in_thinking = True

            if out_text:
                yield {"event": "content_block_delta", "data": {
                    **data, "delta": {"type": "text_delta", "text": out_text}
                }}
            if out_thinking:
                # 简化处理：以 thinking_delta 形式带出
                yield {"event": "content_block_delta", "data": {
                    **data, "delta": {"type": "thinking_delta", "thinking": out_thinking}
                }}
        # 收尾
        if buffer:
            kind = "thinking_delta" if in_thinking else "text_delta"
            key = "thinking" if in_thinking else "text"
            yield {"event": "content_block_delta", "data": {
                "index": 0, "delta": {"type": kind, key: buffer}
            }}
