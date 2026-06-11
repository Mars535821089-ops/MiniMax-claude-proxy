"""中间件 #5: SSE 稳定性。

策略：
1. **心跳 ping**：每 N 秒发 `: ping\\n\\n` 注释行，防代理切断。
2. **tool_use 整块缓冲**：把 input_json_delta 拼成完整 JSON 后一次性发出，避免 Claude Code 解析中途失败。
3. **usage 占位**：在 message_start 补 `cache_creation_input_tokens` / `cache_read_input_tokens` 字段。
4. **重连支持**：每个 event 加 id，客户端可用 Last-Event-ID 续传（实际由 server route 处理）。
"""
from __future__ import annotations
import asyncio
import json
import time
from typing import AsyncIterator, Any
from ..config import SSECfg
from ..utils.logging import get_logger

log = get_logger("sse")


def encode_sse(event: str, data: dict | str, *, event_id: str | None = None) -> bytes:
    """编码单个 SSE 事件为字节。"""
    parts: list[str] = []
    if event_id:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event}")
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    for line in payload.splitlines() or [""]:
        parts.append(f"data: {line}")
    return ("\n".join(parts) + "\n\n").encode("utf-8")


def encode_ping() -> bytes:
    return b": ping\n\n"


class SSEStabilizer:
    def __init__(self, cfg: SSECfg, *, ping_interval: int = 15):
        self.cfg = cfg
        self.ping_interval = ping_interval

    async def wrap(self, events: AsyncIterator[dict], *, ctx: dict) -> AsyncIterator[bytes]:
        """把上游 dict 事件流转换为带稳定性增强的 SSE 字节流。

        - 加入心跳
        - tool_use 缓冲
        - usage 占位
        """
        queue: asyncio.Queue = asyncio.Queue()
        seq = 0

        async def producer():
            nonlocal seq
            tool_buf: dict[int, dict] = {}  # index -> {id, name, json_buf}
            try:
                async for ev in events:
                    name = ev.get("event")
                    data = ev.get("data", {})

                    # 1) message_start 注入 usage 占位
                    if name == "message_start" and self.cfg.inject_cache_usage_placeholder:
                        msg = data.get("message", {})
                        usage = msg.setdefault("usage", {})
                        usage.setdefault("cache_creation_input_tokens",
                                         ctx.get("cache_creation", 0))
                        usage.setdefault("cache_read_input_tokens",
                                         ctx.get("cache_read", 0))

                    # 2) tool_use 缓冲
                    if self.cfg.buffer_tool_use_blocks:
                        if name == "content_block_start":
                            blk = data.get("content_block", {})
                            if blk.get("type") == "tool_use":
                                tool_buf[data.get("index", 0)] = {
                                    "id": blk.get("id"),
                                    "name": blk.get("name"),
                                    "json": "",
                                    "start_event": ev,
                                }
                                continue  # 不外发，等齐
                        if name == "content_block_delta":
                            delta = data.get("delta", {})
                            idx = data.get("index", 0)
                            if delta.get("type") == "input_json_delta" and idx in tool_buf:
                                tool_buf[idx]["json"] += delta.get("partial_json", "")
                                continue
                        if name == "content_block_stop":
                            idx = data.get("index", 0)
                            if idx in tool_buf:
                                buf = tool_buf.pop(idx)
                                # 发完整 start
                                try:
                                    parsed = json.loads(buf["json"]) if buf["json"] else {}
                                except json.JSONDecodeError:
                                    parsed = {"_raw_json": buf["json"]}
                                start_payload = {
                                    "type": "content_block_start",
                                    "index": idx,
                                    "content_block": {
                                        "type": "tool_use",
                                        "id": buf["id"],
                                        "name": buf["name"],
                                        "input": parsed,
                                    },
                                }
                                seq += 1
                                await queue.put((f"e{seq}", "content_block_start", start_payload))
                                # 不再发 delta，直接 stop
                                seq += 1
                                await queue.put((f"e{seq}", "content_block_stop",
                                               {"type": "content_block_stop", "index": idx}))
                                continue

                    seq += 1
                    await queue.put((f"e{seq}", name, data))
            finally:
                await queue.put(None)  # sentinel

        prod_task = asyncio.create_task(producer())
        last_event_at = time.time()

        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=self.ping_interval)
                except asyncio.TimeoutError:
                    yield encode_ping()
                    last_event_at = time.time()
                    continue
                if item is None:
                    break
                eid, event_name, payload = item
                yield encode_sse(event_name, payload, event_id=eid)
                last_event_at = time.time()
        finally:
            prod_task.cancel()
            try:
                await prod_task
            except (asyncio.CancelledError, Exception):
                pass
