"""Anthropic Messages API 数据模型（精简版，够覆盖 Claude Code 实际调用）。"""
from __future__ import annotations
from typing import Any, Literal, Union
from pydantic import BaseModel, Field, ConfigDict


# === Content Blocks ===

class TextBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["text"] = "text"
    text: str
    cache_control: dict | None = None


class ImageSource(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["base64", "url"]
    media_type: str | None = None
    data: str | None = None
    url: str | None = None


class ImageBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["image"] = "image"
    source: ImageSource
    cache_control: dict | None = None


class DocumentSource(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["base64", "url", "text"]
    media_type: str | None = None
    data: str | None = None
    url: str | None = None


class DocumentBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["document"] = "document"
    source: DocumentSource
    title: str | None = None
    context: str | None = None
    cache_control: dict | None = None


class ThinkingBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: str | None = None


class RedactedThinkingBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str


class ToolUseBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Any  # str | list[ContentBlock]
    is_error: bool | None = None
    cache_control: dict | None = None


ContentBlock = Union[
    TextBlock, ImageBlock, DocumentBlock, ThinkingBlock,
    RedactedThinkingBlock, ToolUseBlock, ToolResultBlock,
]


# === Message / Request / Response ===

class Message(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: Literal["user", "assistant"]
    content: Any  # str | list[ContentBlock dict]


class ToolDef(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    cache_control: dict | None = None
    type: str | None = None  # 用于 server-side tools 如 "web_search_20250305"


class ThinkingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["enabled", "disabled"] = "enabled"
    budget_tokens: int = 8192


class MessagesRequest(BaseModel):
    """Anthropic /v1/messages 请求。"""
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    model: str
    messages: list[dict[str, Any]]
    system: Any = None
    max_tokens: int = 4096
    metadata: dict | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict | None = None
    thinking: dict | None = None
    # 任意附加字段保留
    extra: dict = Field(default_factory=dict)


class Usage(BaseModel):
    model_config = ConfigDict(extra="allow")
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


class MessagesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    model: str
    content: list[dict[str, Any]]
    stop_reason: str | None = None
    stop_sequence: str | None = None
    usage: Usage = Field(default_factory=Usage)
