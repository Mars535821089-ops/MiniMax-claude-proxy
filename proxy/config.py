"""配置加载 —— YAML + 环境变量覆盖。"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, Field


class ServerCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8787
    log_level: str = "INFO"
    log_file: str | None = None
    sse_ping_interval: int = 15
    request_timeout: int = 1800


class UpstreamCfg(BaseModel):
    base_url: str
    api_key: str
    model_id: str = "MiniMax-M3"
    max_connections: int = 32
    max_retries: int = 3
    retry_backoff_seconds: float = 2.0

    def model_post_init(self, _: Any) -> None:
        # HTTP header 必须是 ASCII；若 api_key 含非 ASCII 立即报错（避免 cryptic httpx error）
        try:
            self.api_key.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError(
                f"upstream.api_key 含非 ASCII 字符。请编辑 config.yaml 把占位文字"
                f"替换为真实的 MiniMax API Key（以 sk-cp- 开头的纯 ASCII 字符串）。"
            )
        if "填您的" in self.api_key or "your-key-here" in self.api_key:
            raise ValueError(
                "upstream.api_key 是占位文本，请在 config.yaml 填入真实 API Key。"
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError(f"upstream.base_url 必须以 http(s):// 开头：{self.base_url}")


class CacheCfg(BaseModel):
    enabled: bool = True
    backend: str = "sqlite"  # sqlite | memory
    db_path: str = "~/.MiniMax-claude-proxy/cache.db"
    strategy: str = "prefix"  # strict | prefix
    default_ttl: int = 300
    long_ttl: int = 3600
    max_entries: int = 10000


class ThinkingCfg(BaseModel):
    enabled: bool = True
    injection: str = "system_prompt"  # system_prompt | user_prefix
    open_tag: str = "<thinking>"
    close_tag: str = "</thinking>"
    default_budget: int = 8192


class WebSearchCfg(BaseModel):
    backend: str = "duckduckgo"
    max_results: int = 5
    timeout: int = 10


class CodeExecCfg(BaseModel):
    backend: str = "subprocess"
    timeout: int = 30
    memory_limit_mb: int = 512


class ServerSideToolsCfg(BaseModel):
    enabled: bool = True
    enable_web_search: bool = True
    enable_code_execution: bool = True
    enable_bash: bool = False
    web_search: WebSearchCfg = WebSearchCfg()
    code_execution: CodeExecCfg = CodeExecCfg()


class SchemaCfg(BaseModel):
    enabled: bool = True
    flatten_oneof: bool = True
    flatten_anyof: bool = True
    expand_refs: bool = True
    max_depth: int = 5
    reconcile_response: bool = True


class ImageMMCfg(BaseModel):
    max_size_mb: int = 20
    auto_resize: bool = True
    target_long_edge: int = 1568


class PDFCfg(BaseModel):
    strategy: str = "text_and_images"
    max_pages: int = 50
    image_pages_threshold: int = 5


class AVCfg(BaseModel):
    route_via_mcp: bool = True
    mcp_endpoint: str = "http://127.0.0.1:8765"


class MultimodalCfg(BaseModel):
    enabled: bool = True
    image: ImageMMCfg = ImageMMCfg()
    pdf: PDFCfg = PDFCfg()
    audio_video: AVCfg = AVCfg()


class SSECfg(BaseModel):
    buffer_tool_use_blocks: bool = True
    max_event_bytes: int = 65536
    reconnect_window: int = 60
    inject_cache_usage_placeholder: bool = True


class Settings(BaseModel):
    server: ServerCfg = ServerCfg()
    upstream: UpstreamCfg
    cache: CacheCfg = CacheCfg()
    thinking: ThinkingCfg = ThinkingCfg()
    server_side_tools: ServerSideToolsCfg = ServerSideToolsCfg()
    schema_: SchemaCfg = Field(default_factory=SchemaCfg, alias="schema")
    multimodal: MultimodalCfg = MultimodalCfg()
    sse: SSECfg = SSECfg()
    model_mapping: dict[str, str] = Field(default_factory=lambda: {"_default": "MiniMax-M3"})

    model_config = {"populate_by_name": True}


_DEFAULT_PATHS = [
    Path.cwd() / "config.yaml",
    Path.home() / ".MiniMax-claude-proxy" / "config.yaml",
    Path(__file__).resolve().parent.parent / "config.yaml",
]


def load(path: str | None = None) -> Settings:
    """加载配置：显式 path > env MINIMAX_PROXY_CONFIG > 默认搜索路径。"""
    target: Path | None = None
    if path:
        target = Path(path).expanduser()
    elif env := os.getenv("MINIMAX_PROXY_CONFIG"):
        target = Path(env).expanduser()
    else:
        for cand in _DEFAULT_PATHS:
            if cand.exists():
                target = cand
                break

    if not target or not target.exists():
        raise FileNotFoundError(
            "找不到 config.yaml。请复制 config.yaml.example 为 config.yaml 并填入 API Key。"
        )

    raw: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    raw = _env_override(raw)
    return Settings.model_validate(raw)


def _env_override(raw: dict[str, Any]) -> dict[str, Any]:
    """允许用 MINIMAX_API_KEY / MINIMAX_BASE_URL / MINIMAX_PROXY_PORT 覆盖。"""
    raw.setdefault("upstream", {})
    if k := os.getenv("MINIMAX_API_KEY"):
        raw["upstream"]["api_key"] = k
    if u := os.getenv("MINIMAX_BASE_URL"):
        raw["upstream"]["base_url"] = u
    raw.setdefault("server", {})
    if p := os.getenv("MINIMAX_PROXY_PORT"):
        raw["server"]["port"] = int(p)
    if h := os.getenv("MINIMAX_PROXY_HOST"):
        raw["server"]["host"] = h
    return raw
