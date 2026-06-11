"""上游 MiniMax Anthropic 兼容接口客户端 —— httpx 异步 + 流式 + 重试。"""
from __future__ import annotations
import asyncio
import json
from typing import AsyncIterator, Any
import httpx
from .config import UpstreamCfg
from .utils.logging import get_logger

log = get_logger("upstream")


class UpstreamError(Exception):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"upstream {status}: {body[:300]}")


class UpstreamClient:
    """异步上游客户端，连接复用 + 退避重试 + 流式 SSE。"""

    def __init__(self, cfg: UpstreamCfg, *, timeout: float = 1800.0):
        self.cfg = cfg
        limits = httpx.Limits(
            max_connections=cfg.max_connections,
            max_keepalive_connections=cfg.max_connections,
        )
        self._client = httpx.AsyncClient(
            base_url=cfg.base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, connect=30.0),
            limits=limits,
            headers=self._default_headers(),
        )

    def _default_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.cfg.api_key,
            "authorization": f"Bearer {self.cfg.api_key}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    async def close(self) -> None:
        await self._client.aclose()

    # === 非流式 ===
    async def messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            try:
                resp = await self._client.post("/v1/messages", json=payload)
                if resp.status_code >= 500:
                    raise UpstreamError(resp.status_code, resp.text)
                if resp.status_code >= 400:
                    # 4xx 不重试
                    raise UpstreamError(resp.status_code, resp.text)
                return resp.json()
            except (httpx.TransportError, UpstreamError) as e:
                last_err = e
                if isinstance(e, UpstreamError) and 400 <= e.status < 500:
                    raise
                wait = self.cfg.retry_backoff_seconds * (2 ** attempt)
                log.warning(f"upstream attempt {attempt+1} failed: {e!r}, retry in {wait}s")
                await asyncio.sleep(wait)
        raise last_err or RuntimeError("upstream unreachable")

    # === 流式 SSE ===
    async def stream_messages(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """yield parsed SSE events as dicts: {event: str, data: dict}"""
        payload = {**payload, "stream": True}
        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            try:
                async with self._client.stream(
                    "POST", "/v1/messages", json=payload,
                    headers={"accept": "text/event-stream"},
                ) as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        raise UpstreamError(resp.status_code, body.decode("utf-8", "ignore"))
                    async for ev in _parse_sse(resp.aiter_lines()):
                        yield ev
                    return
            except (httpx.TransportError, UpstreamError) as e:
                last_err = e
                if isinstance(e, UpstreamError) and 400 <= e.status < 500:
                    raise
                wait = self.cfg.retry_backoff_seconds * (2 ** attempt)
                log.warning(f"upstream stream attempt {attempt+1} failed: {e!r}, retry in {wait}s")
                await asyncio.sleep(wait)
        raise last_err or RuntimeError("upstream stream unreachable")


async def _parse_sse(line_iter: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
    """解析 SSE 行流为 {event, data} 字典。"""
    event_name: str | None = None
    data_buf: list[str] = []
    async for raw in line_iter:
        line = raw.rstrip("\r")
        if line == "":
            # 事件分隔
            if data_buf:
                data_str = "\n".join(data_buf)
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    data = {"_raw": data_str}
                yield {"event": event_name or "message", "data": data}
            event_name = None
            data_buf = []
            continue
        if line.startswith(":"):
            continue  # comment / heartbeat
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_buf.append(line[5:].lstrip())
        # 其他字段忽略
