"""MiniMax Claude Proxy — FastAPI 主入口。

工作流（请求 /v1/messages）：
  client ──► main.handle ──► [model_mapping] ──► [cache.strip + read]
       ──► [thinking.preprocess] ──► [schema.preprocess]
       ──► [server_side_tools.preprocess] ──► [multimodal.preprocess]
       ──► upstream(MiniMax-M3) ──► [sse.wrap + thinking.stream + cache.put]
       ──► client
"""
from __future__ import annotations
import argparse
import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from . import __version__
from .config import Settings, load as load_settings
from .upstream import UpstreamClient, UpstreamError
from .middleware.cache import CacheStore
from .middleware.thinking import ThinkingShim
from .middleware.schema import SchemaShim
from .middleware.multimodal import MultimodalShim
from .middleware.sse import SSEStabilizer, encode_sse
from .tools.registry import ServerSideToolsHub
from .utils.logging import setup_logging, get_logger

log = get_logger("main")


class ProxyApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.upstream = UpstreamClient(settings.upstream, timeout=settings.server.request_timeout)
        self.cache = CacheStore(settings.cache)
        self.thinking = ThinkingShim(settings.thinking)
        self.schema = SchemaShim(settings.schema_)
        self.multimodal = MultimodalShim(settings.multimodal)
        self.ssr_tools = ServerSideToolsHub(settings.server_side_tools)
        self.sse = SSEStabilizer(settings.sse, ping_interval=settings.server.sse_ping_interval)

    async def close(self):
        await self.upstream.close()
        await self.multimodal.close()

    # === 模型 ID 重映射 ===
    def map_model(self, req_model: str) -> str:
        mp = self.settings.model_mapping
        return mp.get(req_model) or mp.get("_default") or self.settings.upstream.model_id

    # === 完整 pipeline ===
    async def pipeline(self, payload: dict) -> tuple[dict, dict]:
        """前置处理 pipeline。返回 (清洗后的 payload, 上下文 ctx)。

        注意：本方法不 mutate 入参（深拷贝防止缓存键漂移）。
        """
        import copy
        payload = copy.deepcopy(payload)
        ctx: dict[str, Any] = {}

        # 1) 模型映射
        original_model = payload.get("model", "")
        payload["model"] = self.map_model(original_model)
        ctx["original_model"] = original_model

        # 2) cache_control 剥离
        payload = self.cache.strip_cache_control(payload)

        # 3) thinking 模拟
        payload, t_ctx = self.thinking.preprocess_request(payload)
        ctx["thinking"] = t_ctx

        # 4) schema 简化
        payload, s_ctx = self.schema.preprocess_request(payload)
        ctx["schema"] = s_ctx

        # 5) server-side tools 翻译
        payload, ssr_ctx = self.ssr_tools.preprocess_request(payload)
        ctx["ssr_tools"] = ssr_ctx

        # 6) 多模态预处理
        payload = await self.multimodal.preprocess_request(payload)

        # 7) prefix 缓存命中统计（注入 usage 占位）
        approx_input = _approx_input_tokens(payload)
        creation, read = await self.cache.touch_prefix(
            payload.get("messages", []),
            payload.get("system"),
            payload.get("tools"),
            approx_input,
        )
        ctx["cache_creation"] = creation
        ctx["cache_read"] = read

        return payload, ctx

    # === 非流式 ===
    async def handle_messages(self, payload: dict) -> dict:
        # 缓存 key 使用 cleaned payload（pipeline 之后），保证 GET 与 PUT key 一致
        cleaned, ctx = await self.pipeline(payload)

        cached = await self.cache.get_response(cleaned)
        if cached:
            log.info("response cache HIT, skip upstream")
            return cached

        response = await self.upstream.messages(cleaned)

        # 后置处理
        response = self.thinking.postprocess_response(response, ctx["thinking"])
        response = self.schema.postprocess_response(response, ctx["schema"])

        # server-side tool 拦截：如果模型给了某个本地实现工具的 tool_use，本轮直接执行并合成第二轮
        ssr_map = ctx["ssr_tools"]
        if ssr_map:
            executed = await self._maybe_execute_ssr(response, cleaned, ssr_map)
            if executed:
                response = executed

        # 注入 cache usage
        usage = response.setdefault("usage", {})
        usage.setdefault("cache_creation_input_tokens", ctx["cache_creation"])
        usage.setdefault("cache_read_input_tokens", ctx["cache_read"])

        # 写缓存
        await self.cache.put_response(cleaned, response)
        return response

    async def _maybe_execute_ssr(self, response: dict, payload: dict, ssr_map: dict) -> dict | None:
        """如果响应里有 server-side tool_use，本地执行后再调一轮模型生成最终答案。"""
        tool_calls = [b for b in response.get("content", []) if b.get("type") == "tool_use"]
        hits = [c for c in tool_calls if c.get("name") in ssr_map]
        if not hits:
            return None

        log.info(f"intercepting server-side tools: {[c['name'] for c in hits]}")
        # 构建下一轮 messages
        new_messages = list(payload.get("messages", []))
        new_messages.append({"role": "assistant", "content": response.get("content", [])})
        user_blocks: list[dict] = []
        for c in hits:
            result = await self.ssr_tools.execute(c["name"], ssr_map[c["name"]], c.get("input", {}))
            user_blocks.append({
                "type": "tool_result",
                "tool_use_id": c.get("id", ""),
                "content": result["content"],
                **({"is_error": True} if result.get("is_error") else {}),
            })
        new_messages.append({"role": "user", "content": user_blocks})

        round2 = {**payload, "messages": new_messages}
        try:
            return await self.upstream.messages(round2)
        except UpstreamError as e:
            log.error(f"round2 fail: {e}")
            return None

    # === 流式 ===
    async def handle_messages_stream(self, payload: dict):
        cleaned, ctx = await self.pipeline(payload)

        async def upstream_events():
            async for ev in self.upstream.stream_messages(cleaned):
                yield ev

        # thinking 流转换
        transformer = self.thinking.stream_transformer(ctx["thinking"])
        events = transformer(upstream_events())

        # SSE 稳定性包装
        async for chunk in self.sse.wrap(events, ctx=ctx):
            yield chunk


def _approx_input_tokens(payload: dict) -> int:
    """粗略估算输入 token 数（用于 cache 统计占位）。"""
    text = json.dumps(payload, ensure_ascii=False)
    # 经验：中英混合 ~3 chars per token
    return max(1, len(text) // 3)


# === FastAPI 工厂 ===
def create_app(settings: Settings) -> FastAPI:
    state = ProxyApp(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await state.cache.init()
        log.info(f"MiniMax-claude-proxy v{__version__} listening on "
                 f"{settings.server.host}:{settings.server.port}")
        log.info(f"upstream → {settings.upstream.base_url} model={settings.upstream.model_id}")
        yield
        await state.close()

    app = FastAPI(title="MiniMax Claude Proxy", version=__version__, lifespan=lifespan)

    @app.get("/")
    async def root():
        return {"service": "MiniMax-claude-proxy", "version": __version__, "status": "ok"}

    @app.get("/v1/health")
    async def health():
        return {"status": "ok", "upstream": settings.upstream.base_url}

    @app.post("/v1/messages/count_tokens")
    async def count_tokens(req: Request):
        """Claude Code 会调这个端点估 token。本地用经验值返回，避免 404。"""
        body = await req.json()
        approx = _approx_input_tokens(body)
        return {"input_tokens": approx}

    @app.post("/v1/messages")
    async def messages(req: Request):
        try:
            payload = await req.json()
        except Exception:
            raise HTTPException(400, "invalid json body")

        stream = bool(payload.get("stream"))
        req_id = req.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
        log.info(f"[{req_id}] /v1/messages stream={stream} model={payload.get('model')} "
                 f"messages={len(payload.get('messages', []))} tools={len(payload.get('tools', []) or [])}")
        t0 = time.time()

        if not stream:
            try:
                resp = await state.handle_messages(payload)
            except UpstreamError as e:
                return JSONResponse({"type": "error", "error": {"type": "upstream_error",
                                    "message": str(e.body)}}, status_code=e.status)
            except Exception as e:
                log.exception(f"[{req_id}] non-stream fail: {e}")
                return JSONResponse({"type": "error", "error": {"type": "internal_error",
                                    "message": str(e)}}, status_code=500)
            log.info(f"[{req_id}] done in {time.time()-t0:.2f}s tokens={resp.get('usage',{})}")
            return JSONResponse(resp)

        async def event_stream():
            try:
                async for chunk in state.handle_messages_stream(payload):
                    yield chunk
            except UpstreamError as e:
                yield encode_sse("error", {"type": "error", "error": {
                    "type": "upstream_error", "message": str(e.body)}})
            except Exception as e:
                log.exception(f"[{req_id}] stream fail: {e}")
                yield encode_sse("error", {"type": "error", "error": {
                    "type": "internal_error", "message": str(e)}})
            finally:
                log.info(f"[{req_id}] stream done in {time.time()-t0:.2f}s")

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "cache-control": "no-cache",
                "x-accel-buffering": "no",
                "connection": "keep-alive",
            },
        )

    app.state.proxy = state
    return app


# === CLI ===
def cli():
    p = argparse.ArgumentParser("MiniMax-claude-proxy")
    p.add_argument("--config", "-c", help="path to config.yaml")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--reload", action="store_true", help="dev mode auto-reload")
    args = p.parse_args()

    settings = load_settings(args.config)
    if args.host:
        settings.server.host = args.host
    if args.port:
        settings.server.port = args.port

    setup_logging(settings.server.log_level, settings.server.log_file)
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.server.host,
        port=settings.server.port,
        log_level=settings.server.log_level.lower(),
        reload=args.reload,
        timeout_keep_alive=settings.server.request_timeout,
    )


if __name__ == "__main__":
    cli()
