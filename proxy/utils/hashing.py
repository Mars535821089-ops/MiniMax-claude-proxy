"""Hash 工具 —— 用于缓存键计算、SSE event_id 生成等。"""
from __future__ import annotations
import hashlib
import json
from typing import Any


def stable_dict_hash(obj: Any, *, length: int = 16) -> str:
    """对任意 JSON 可序列化对象稳定哈希。"""
    encoded = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.blake2b(encoded, digest_size=length).hexdigest()


def prefix_hash(messages: list[dict], system: Any, tools: list[dict] | None, *, length: int = 24) -> str:
    """计算 (system + tools + messages[:-1]) 的稳定哈希作为前缀键。

    最后一条 user 消息不参与，方便对相同上下文不同末轮做命中比对。
    """
    payload = {
        "system": _normalize(system),
        "tools": _normalize(tools or []),
        "messages": _normalize(messages[:-1] if messages else []),
    }
    return stable_dict_hash(payload, length=length)


def full_request_hash(payload: dict, *, length: int = 24) -> str:
    """对完整请求计算哈希用于幂等去重。"""
    blacklist = {"stream", "metadata"}
    cleaned = {k: v for k, v in payload.items() if k not in blacklist}
    return stable_dict_hash(_normalize(cleaned), length=length)


def _normalize(obj: Any) -> Any:
    """把不可比对的字段（如 cache_control）剥离，避免影响命中率。"""
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items() if k != "cache_control"}
    if isinstance(obj, list):
        return [_normalize(x) for x in obj]
    return obj
