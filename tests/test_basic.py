"""基础烟雾测试 —— 不依赖网络，验证中间件函数纯逻辑。"""
from __future__ import annotations
import asyncio
import json
import pytest

from proxy.config import (
    CacheCfg, ThinkingCfg, SchemaCfg, ServerSideToolsCfg, MultimodalCfg, SSECfg,
)
from proxy.middleware.cache import CacheStore
from proxy.middleware.thinking import ThinkingShim
from proxy.middleware.schema import SchemaShim
from proxy.middleware.sse import encode_sse, SSEStabilizer
from proxy.tools.registry import ServerSideToolsHub


# === cache_control 剥离 ===
def test_strip_cache_control_recursive():
    payload = {
        "model": "x",
        "system": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "q", "cache_control": {}}]},
        ],
        "tools": [{"name": "t", "cache_control": {}}],
    }
    cleaned = CacheStore.strip_cache_control(payload)
    s = json.dumps(cleaned)
    assert "cache_control" not in s


# === thinking 注入 ===
def test_thinking_inject_system():
    shim = ThinkingShim(ThinkingCfg())
    payload = {"system": "You are helpful.", "thinking": {"type": "enabled", "budget_tokens": 1024}}
    new_payload, ctx = shim.preprocess_request(payload)
    assert ctx["enabled"]
    assert "thinking" not in new_payload
    assert "推理模式" in new_payload["system"]


def test_thinking_split_text_block():
    shim = ThinkingShim(ThinkingCfg())
    text = "前面<thinking>这是推理过程</thinking>这是回答<thinking>再想想</thinking>结尾"
    blocks = shim._split_text_block(text)
    types = [b["type"] for b in blocks]
    assert types == ["text", "thinking", "text", "thinking", "text"]
    assert blocks[1]["thinking"] == "这是推理过程"


# === schema 简化 ===
def test_schema_flatten_oneof():
    shim = SchemaShim(SchemaCfg())
    payload = {
        "tools": [{
            "name": "t",
            "input_schema": {
                "type": "object",
                "properties": {
                    "x": {"oneOf": [{"type": "string"}, {"type": "number"}]}
                }
            }
        }]
    }
    new_payload, ctx = shim.preprocess_request(payload)
    schema = new_payload["tools"][0]["input_schema"]
    assert schema["properties"]["x"]["type"] == "string"
    assert "ctx" or ctx["tool_originals"]["t"]


def test_schema_reconcile_string_to_object():
    shim = SchemaShim(SchemaCfg())
    schema = {"type": "object", "properties": {"data": {"type": "object"}}}
    out = shim._reconcile({"data": '{"a": 1}'}, schema)
    assert out["data"] == {"a": 1}


# === server-side tools ===
def test_ssr_tools_translate_web_search():
    hub = ServerSideToolsHub(ServerSideToolsCfg())
    payload = {"tools": [{"type": "web_search_20250305", "name": "web_search"}]}
    new_payload, ctx = hub.preprocess_request(payload)
    assert ctx["web_search"] == "web_search"
    assert new_payload["tools"][0]["name"] == "web_search"
    assert "input_schema" in new_payload["tools"][0]


# === SSE 编码 ===
def test_encode_sse_basic():
    out = encode_sse("message_start", {"type": "message_start", "message": {}}, event_id="e1")
    s = out.decode()
    assert "id: e1" in s
    assert "event: message_start" in s
    assert "data: " in s
    assert s.endswith("\n\n")


# === SSE 整流：tool_use 缓冲 ===
@pytest.mark.asyncio
async def test_sse_stabilizer_buffers_tool_use():
    cfg = SSECfg()
    stab = SSEStabilizer(cfg, ping_interval=999)  # 不要心跳干扰

    async def events():
        yield {"event": "message_start", "data": {"type": "message_start", "message": {}}}
        yield {"event": "content_block_start", "data": {
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "tu1", "name": "foo"}
        }}
        yield {"event": "content_block_delta", "data": {
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"a"'}
        }}
        yield {"event": "content_block_delta", "data": {
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": ': 1}'}
        }}
        yield {"event": "content_block_stop", "data": {
            "type": "content_block_stop", "index": 0
        }}
        yield {"event": "message_stop", "data": {"type": "message_stop"}}

    chunks: list[bytes] = []
    async for c in stab.wrap(events(), ctx={"cache_creation": 0, "cache_read": 0}):
        chunks.append(c)

    full = b"".join(chunks).decode()
    # 应该出现合并好的 input
    assert '"input"' in full
    assert '"a": 1' in full or '"a":1' in full


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
