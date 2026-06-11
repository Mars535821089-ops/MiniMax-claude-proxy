"""Mock 上游 + E2E 集成测试。

启动两个 FastAPI 进程（用 asyncio 内嵌）：
- 8911: 假 MiniMax 上游
- 8912: 真 proxy 指向假上游

然后用 httpx 发请求到 proxy，验证 6 大块功能。
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# 让 proxy 模块可导入
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from proxy.main import create_app
from proxy.config import Settings, ServerCfg, UpstreamCfg, CacheCfg, ThinkingCfg, \
    SchemaCfg, ServerSideToolsCfg, MultimodalCfg, SSECfg, WebSearchCfg, CodeExecCfg


# ============ Mock 上游：假装是 MiniMax ============

mock_app = FastAPI(title="mock-MiniMax-upstream")
mock_state = {
    "calls": [],            # 记录所有收到的请求
    "next_response": None,  # 强制下一次返回内容
    "next_stream_events": None,  # 强制下一次 stream 事件
}


@mock_app.post("/v1/messages")
async def mock_messages(req: Request):
    body = await req.json()
    mock_state["calls"].append(body)

    stream = bool(body.get("stream"))
    if stream:
        events = mock_state.get("next_stream_events") or _default_stream_events(body)
        async def gen():
            for ev_name, ev_data in events:
                yield f"event: {ev_name}\ndata: {json.dumps(ev_data)}\n\n".encode()
                await asyncio.sleep(0.005)
        return StreamingResponse(gen(), media_type="text/event-stream")

    if mock_state.get("next_response"):
        return JSONResponse(mock_state["next_response"])
    return JSONResponse(_default_response(body))


def _default_response(body: dict) -> dict:
    user_text = ""
    msgs = body.get("messages", [])
    if msgs:
        last = msgs[-1]
        c = last.get("content")
        if isinstance(c, str):
            user_text = c
        elif isinstance(c, list):
            for b in c:
                if b.get("type") == "text":
                    user_text = b.get("text", "")
                    break
    return {
        "id": "msg_mock_001",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "MiniMax-M3"),
        "content": [{"type": "text", "text": f"echo: {user_text}"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _default_stream_events(body: dict) -> list[tuple[str, dict]]:
    return [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_mock_str", "type": "message", "role": "assistant",
            "model": body.get("model", "MiniMax-M3"),
            "content": [], "stop_reason": None,
            "usage": {"input_tokens": 10, "output_tokens": 0},
        }}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "Hi "}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "there"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                          "usage": {"output_tokens": 5}}),
        ("message_stop", {"type": "message_stop"}),
    ]


# ============ 启动两个服务器作为 fixture ============

class _ServerCtx:
    def __init__(self, app, host: str, port: int):
        self.config = uvicorn.Config(app, host=host, port=port, log_level="warning",
                                     lifespan="on")
        self.server = uvicorn.Server(self.config)
        self.task: asyncio.Task | None = None
        self.host, self.port = host, port

    async def start(self):
        self.task = asyncio.create_task(self.server.serve())
        # 等待 ready
        for _ in range(80):
            await asyncio.sleep(0.05)
            if self.server.started:
                return
        raise RuntimeError(f"server {self.port} failed to start")

    async def stop(self):
        self.server.should_exit = True
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=5)
            except Exception:
                pass


def _make_proxy_settings(upstream_port: int, tmp_db: str) -> Settings:
    return Settings(
        server=ServerCfg(host="127.0.0.1", port=8912, log_level="WARNING",
                        sse_ping_interval=2, request_timeout=60),
        upstream=UpstreamCfg(
            base_url=f"http://127.0.0.1:{upstream_port}",
            api_key="test-key", model_id="MiniMax-M3",
            max_retries=1, retry_backoff_seconds=0.1,
        ),
        cache=CacheCfg(enabled=True, backend="sqlite", db_path=tmp_db,
                      default_ttl=60, max_entries=100),
        thinking=ThinkingCfg(enabled=True),
        server_side_tools=ServerSideToolsCfg(
            enabled=True, enable_web_search=True, enable_code_execution=True,
            web_search=WebSearchCfg(backend="duckduckgo", timeout=5),
            code_execution=CodeExecCfg(timeout=5),
        ),
        multimodal=MultimodalCfg(enabled=True),
        sse=SSECfg(),
        model_mapping={"_default": "MiniMax-M3", "claude-opus-4-6": "MiniMax-M3"},
    )


@pytest_asyncio.fixture
async def servers():
    """启 mock 上游 + proxy，结束时优雅关闭。"""
    mock_state["calls"].clear()
    mock_state["next_response"] = None
    mock_state["next_stream_events"] = None

    tmp_db = str(Path(tempfile.gettempdir()) / f"MiniMax_test_cache_{int(time.time()*1000)}.db")
    settings = _make_proxy_settings(8911, tmp_db)
    proxy_app = create_app(settings)

    upstream = _ServerCtx(mock_app, "127.0.0.1", 8911)
    proxy = _ServerCtx(proxy_app, "127.0.0.1", 8912)
    await upstream.start()
    await proxy.start()
    try:
        yield {
            "proxy_url": "http://127.0.0.1:8912",
            "upstream_url": "http://127.0.0.1:8911",
            "settings": settings,
        }
    finally:
        await proxy.stop()
        await upstream.stop()
        try:
            os.unlink(tmp_db)
        except FileNotFoundError:
            pass


# ============ E2E 测试 ============

HEADERS = {
    "x-api-key": "any",
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}


@pytest.mark.asyncio
async def test_e2e_health(servers):
    """① 健康端点存活。"""
    async with httpx.AsyncClient() as cli:
        r = await cli.get(f"{servers['proxy_url']}/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_e2e_count_tokens(servers):
    """② count_tokens 端点（Claude Code 会调用）。"""
    async with httpx.AsyncClient() as cli:
        r = await cli.post(
            f"{servers['proxy_url']}/v1/messages/count_tokens",
            json={"messages": [{"role": "user", "content": "hello world"}]},
            headers=HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["input_tokens"] > 0


@pytest.mark.asyncio
async def test_e2e_basic_non_stream(servers):
    """③ 基础非流式请求 → 上游返回 → proxy 回流。"""
    async with httpx.AsyncClient() as cli:
        r = await cli.post(
            f"{servers['proxy_url']}/v1/messages",
            json={
                "model": "claude-opus-4-6",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "ping"}],
            },
            headers=HEADERS,
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["content"][0]["text"] == "echo: ping"
        # 验证模型映射生效
        sent = mock_state["calls"][-1]
        assert sent["model"] == "MiniMax-M3"


@pytest.mark.asyncio
async def test_e2e_cache_control_stripped(servers):
    """④ cache_control 应被剥离后再发给上游。"""
    async with httpx.AsyncClient() as cli:
        await cli.post(
            f"{servers['proxy_url']}/v1/messages",
            json={
                "model": "MiniMax-M3", "max_tokens": 100,
                "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=HEADERS, timeout=10,
        )
    sent = mock_state["calls"][-1]
    assert "cache_control" not in json.dumps(sent)


@pytest.mark.asyncio
async def test_e2e_thinking_injected(servers):
    """⑤ thinking 配置应被剥离，system 注入引导。"""
    async with httpx.AsyncClient() as cli:
        await cli.post(
            f"{servers['proxy_url']}/v1/messages",
            json={
                "model": "MiniMax-M3", "max_tokens": 100,
                "thinking": {"type": "enabled", "budget_tokens": 1024},
                "system": "Be concise.",
                "messages": [{"role": "user", "content": "Q?"}],
            },
            headers=HEADERS, timeout=10,
        )
    sent = mock_state["calls"][-1]
    assert "thinking" not in sent
    assert "推理模式" in (sent.get("system") or "")


@pytest.mark.asyncio
async def test_e2e_schema_oneof_flattened(servers):
    """⑥ tool schema 中的 oneOf 应被拍平。"""
    async with httpx.AsyncClient() as cli:
        await cli.post(
            f"{servers['proxy_url']}/v1/messages",
            json={
                "model": "MiniMax-M3", "max_tokens": 100,
                "messages": [{"role": "user", "content": "use tool"}],
                "tools": [{
                    "name": "t1",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "v": {"oneOf": [{"type": "string"}, {"type": "number"}]}
                        }
                    }
                }],
            },
            headers=HEADERS, timeout=10,
        )
    sent = mock_state["calls"][-1]
    schema = sent["tools"][0]["input_schema"]
    assert "oneOf" not in schema["properties"]["v"]
    assert schema["properties"]["v"]["type"] == "string"


@pytest.mark.asyncio
async def test_e2e_ssr_tool_translated(servers):
    """⑦ server-side tool web_search_20250305 应被翻译为普通工具。"""
    async with httpx.AsyncClient() as cli:
        await cli.post(
            f"{servers['proxy_url']}/v1/messages",
            json={
                "model": "MiniMax-M3", "max_tokens": 100,
                "messages": [{"role": "user", "content": "search foo"}],
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            },
            headers=HEADERS, timeout=10,
        )
    sent = mock_state["calls"][-1]
    t = sent["tools"][0]
    # type 应被去掉 / 转成 普通工具
    assert "input_schema" in t
    assert t["name"] == "web_search"


@pytest.mark.asyncio
async def test_e2e_cache_hit_second_call(servers):
    """⑧ 同样的请求二次调用应命中响应缓存（mock 上游只被调用一次）。"""
    payload = {
        "model": "MiniMax-M3", "max_tokens": 100,
        "messages": [{"role": "user", "content": "cache me"}],
    }
    async with httpx.AsyncClient() as cli:
        r1 = await cli.post(f"{servers['proxy_url']}/v1/messages",
                           json=payload, headers=HEADERS, timeout=10)
        r2 = await cli.post(f"{servers['proxy_url']}/v1/messages",
                           json=payload, headers=HEADERS, timeout=10)
    assert r1.json() == r2.json()
    # 上游只该被调一次
    calls = [c for c in mock_state["calls"]
             if c.get("messages", [{}])[-1].get("content") == "cache me"]
    assert len(calls) == 1, f"expected 1 upstream call, got {len(calls)}"


@pytest.mark.asyncio
async def test_e2e_cache_hit_with_claude_model_mapping(servers):
    """⑧.5 回归测试：原始请求带 claude-* model id，二次调用应仍命中缓存。

    之前的 bug：pipeline 直接 mutate payload['model'] 把 'claude-opus-4-6'
    改成了 'MiniMax-M3'，导致 GET key（原始 model）和 PUT key（mutate 后）漂移。
    """
    payload = {
        "model": "claude-opus-4-6", "max_tokens": 100,
        "messages": [{"role": "user", "content": "regression: same key please"}],
    }
    async with httpx.AsyncClient() as cli:
        r1 = await cli.post(f"{servers['proxy_url']}/v1/messages",
                           json=payload, headers=HEADERS, timeout=10)
        r2 = await cli.post(f"{servers['proxy_url']}/v1/messages",
                           json=payload, headers=HEADERS, timeout=10)
    assert r1.json() == r2.json()
    calls = [c for c in mock_state["calls"]
             if c.get("messages", [{}])[-1].get("content") == "regression: same key please"]
    assert len(calls) == 1, f"cache mutation regression: expected 1 upstream call, got {len(calls)}"


@pytest.mark.asyncio
async def test_e2e_streaming_basic(servers):
    """⑨ 流式请求 → 正确转发 SSE 事件。"""
    async with httpx.AsyncClient(timeout=20) as cli:
        async with cli.stream(
            "POST", f"{servers['proxy_url']}/v1/messages",
            json={
                "model": "MiniMax-M3", "max_tokens": 100, "stream": True,
                "messages": [{"role": "user", "content": "stream"}],
            },
            headers=HEADERS,
        ) as resp:
            assert resp.status_code == 200
            chunks: list[bytes] = []
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                if b"message_stop" in b"".join(chunks):
                    break
    full = b"".join(chunks).decode()
    assert "event: message_start" in full
    assert "event: content_block_delta" in full
    assert "event: message_stop" in full
    # 心跳 ping 字段（取决于流速）：不强制
    # 检查 cache usage 占位被注入
    assert "cache_creation_input_tokens" in full or "cache_read_input_tokens" in full


@pytest.mark.asyncio
async def test_e2e_streaming_tool_use_buffered(servers):
    """⑩ tool_use 多 partial_json 应被代理整合成单个 input。"""
    mock_state["next_stream_events"] = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_t", "type": "message", "role": "assistant", "model": "MiniMax-M3",
            "content": [], "stop_reason": None,
            "usage": {"input_tokens": 5, "output_tokens": 0},
        }}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "tool_use", "id": "tu_1",
                                                  "name": "calc", "input": {}}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "input_json_delta", "partial_json": '{"x":'}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "input_json_delta", "partial_json": ' 42}'}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
                          "usage": {"output_tokens": 3}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    async with httpx.AsyncClient(timeout=20) as cli:
        async with cli.stream(
            "POST", f"{servers['proxy_url']}/v1/messages",
            json={
                "model": "MiniMax-M3", "max_tokens": 100, "stream": True,
                "messages": [{"role": "user", "content": "calc"}],
                "tools": [{"name": "calc", "input_schema": {
                    "type": "object", "properties": {"x": {"type": "integer"}}
                }}],
            },
            headers=HEADERS,
        ) as resp:
            chunks: list[bytes] = []
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                if b"message_stop" in b"".join(chunks):
                    break
    full = b"".join(chunks).decode()
    # tool_use 应被整块 + 含完整 input
    assert '"tool_use"' in full
    assert '"x"' in full
    assert '42' in full
    # 不应再有 partial_json
    assert "partial_json" not in full


@pytest.mark.asyncio
async def test_e2e_ssr_tool_round2_executes(servers):
    """⑪ 模型调用 web_search 工具时，proxy 拦截并执行 round-2。"""
    # 第一次：模型回 tool_use web_search
    mock_state["next_response"] = {
        "id": "msg_t1", "type": "message", "role": "assistant", "model": "MiniMax-M3",
        "content": [
            {"type": "tool_use", "id": "tu_1", "name": "web_search", "input": {"query": "test"}}
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }
    # 准备 round-2 的响应（用 next_response 复用机制）
    # 这里偷个懒：mock 不会知道 round-2，会走 _default_response 回 echo
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.post(
            f"{servers['proxy_url']}/v1/messages",
            json={
                "model": "MiniMax-M3", "max_tokens": 100,
                "messages": [{"role": "user", "content": "search test"}],
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            },
            headers=HEADERS,
        )
    assert r.status_code == 200
    # 应该至少调了 2 次上游（round-1 触发 tool, round-2 拿结果回答）
    assert len(mock_state["calls"]) >= 2
    round2 = mock_state["calls"][-1]
    # round-2 messages 应该包含 tool_result
    msgs = round2["messages"]
    last_user = msgs[-1]
    assert last_user["role"] == "user"
    content = last_user["content"]
    if isinstance(content, list):
        tool_results = [b for b in content if b.get("type") == "tool_result"]
        assert tool_results, "round-2 must contain tool_result block"


@pytest.mark.asyncio
async def test_e2e_usage_cache_placeholder(servers):
    """⑫ 响应 usage 应包含 cache_* 占位字段。"""
    async with httpx.AsyncClient(timeout=10) as cli:
        r = await cli.post(
            f"{servers['proxy_url']}/v1/messages",
            json={
                "model": "MiniMax-M3", "max_tokens": 100,
                "messages": [{"role": "user", "content": "usage"}],
            },
            headers=HEADERS,
        )
    usage = r.json().get("usage", {})
    assert "cache_creation_input_tokens" in usage
    assert "cache_read_input_tokens" in usage


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
