"""本地实现的 Anthropic server-side web_search 工具。

backends:
- duckduckgo: 免费、无 key，适合默认
- MiniMax_mcp: 走 MiniMax MCP server 的 web_search
- serper: 需要 SERPER_API_KEY
"""
from __future__ import annotations
import os
from typing import Any
import httpx
from ..config import WebSearchCfg
from ..utils.logging import get_logger

log = get_logger("web_search")


async def web_search(query: str, *, cfg: WebSearchCfg) -> list[dict]:
    if cfg.backend == "duckduckgo":
        return await _ddg(query, cfg.max_results, cfg.timeout)
    if cfg.backend == "MiniMax_mcp":
        return await _MiniMax_mcp(query, cfg.max_results, cfg.timeout)
    if cfg.backend == "serper":
        return await _serper(query, cfg.max_results, cfg.timeout)
    return []


async def _ddg(query: str, k: int, timeout: int) -> list[dict]:
    """DuckDuckGo 搜索 —— 优先用新包 ddgs，回退到老包 duckduckgo_search。"""
    import asyncio
    # 新包 ddgs
    try:
        from ddgs import DDGS
        def _run():
            with DDGS(timeout=timeout) as ddgs:
                return list(ddgs.text(query, max_results=k))
        items = await asyncio.to_thread(_run)
        return [
            {"title": it.get("title"), "url": it.get("href"), "snippet": it.get("body")}
            for it in items
        ]
    except ImportError:
        pass
    except Exception as e:
        log.warning(f"ddgs search fail: {e}")
        return []
    # 老包回退
    try:
        from duckduckgo_search import DDGS
        def _run():
            with DDGS(timeout=timeout) as ddgs:
                return list(ddgs.text(query, max_results=k))
        items = await asyncio.to_thread(_run)
        return [
            {"title": it.get("title"), "url": it.get("href"), "snippet": it.get("body")}
            for it in items
        ]
    except ImportError:
        log.warning("neither ddgs nor duckduckgo_search installed")
        return []
    except Exception as e:
        log.warning(f"ddg search fail: {e}")
        return []


async def _MiniMax_mcp(query: str, k: int, timeout: int) -> list[dict]:
    # 通过本地 MiniMax MCP 桥（如果跑着 mcp-proxy）
    base = os.getenv("MINIMAX_MCP_HTTP", "http://127.0.0.1:8765")
    async with httpx.AsyncClient(timeout=timeout) as cli:
        try:
            r = await cli.post(f"{base}/tools/web_search", json={"query": query, "k": k})
            r.raise_for_status()
            return r.json().get("results", [])[:k]
        except Exception as e:
            log.warning(f"MiniMax mcp search fail: {e}")
            return []


async def _serper(query: str, k: int, timeout: int) -> list[dict]:
    key = os.getenv("SERPER_API_KEY")
    if not key:
        return []
    async with httpx.AsyncClient(timeout=timeout) as cli:
        r = await cli.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key},
            json={"q": query, "num": k},
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for it in data.get("organic", [])[:k]:
            out.append({"title": it.get("title"), "url": it.get("link"), "snippet": it.get("snippet")})
        return out


def format_results_as_text(results: list[dict]) -> str:
    if not results:
        return "(no results)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title','(no title)')}\n   {r.get('url','')}\n   {r.get('snippet','')}")
    return "\n".join(lines)
