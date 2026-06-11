"""中间件 #4: 多模态预处理。

策略：
1. **图片**：base64 校验、尺寸自动缩放（长边 1568），URL → base64 拉取。
2. **PDF**：用 PyMuPDF 抽文本；若启用 text_and_images 策略，关键页转图加入。
3. **音频/视频**：路由到 MiniMax MCP（如果可用），否则降级为文本占位。
4. 在 message.content 中就地替换 block。
"""
from __future__ import annotations
import asyncio
import base64
import io
from typing import Any
import httpx

from ..config import MultimodalCfg
from ..utils.logging import get_logger

log = get_logger("multimodal")


class MultimodalShim:
    def __init__(self, cfg: MultimodalCfg):
        self.cfg = cfg
        self._http = httpx.AsyncClient(timeout=60)

    async def close(self) -> None:
        await self._http.aclose()

    async def preprocess_request(self, payload: dict) -> dict:
        if not self.cfg.enabled:
            return payload
        messages = payload.get("messages", [])
        new_msgs = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                new_content = []
                for block in content:
                    processed = await self._process_block(block)
                    if isinstance(processed, list):
                        new_content.extend(processed)
                    else:
                        new_content.append(processed)
                msg = {**msg, "content": new_content}
            new_msgs.append(msg)
        return {**payload, "messages": new_msgs}

    async def _process_block(self, block: dict) -> dict | list[dict]:
        t = block.get("type")
        if t == "image":
            return await self._process_image(block)
        if t == "document":
            return await self._process_document(block)
        return block

    # === 图片 ===
    async def _process_image(self, block: dict) -> dict:
        src = block.get("source", {})
        st = src.get("type")
        if st == "url":
            try:
                resp = await self._http.get(src["url"])
                resp.raise_for_status()
                data_b64 = base64.b64encode(resp.content).decode()
                media = resp.headers.get("content-type", "image/png").split(";")[0]
                block = {**block, "source": {"type": "base64", "media_type": media, "data": data_b64}}
            except Exception as e:
                log.warning(f"image url fetch failed: {e}")
                return {"type": "text", "text": f"[图片加载失败: {src.get('url')}]"}
        # 缩放
        if self.cfg.image.auto_resize and block.get("source", {}).get("type") == "base64":
            block = await asyncio.to_thread(self._maybe_resize_image, block)
        return block

    def _maybe_resize_image(self, block: dict) -> dict:
        try:
            from PIL import Image
        except ImportError:
            return block
        src = block["source"]
        try:
            raw = base64.b64decode(src["data"])
        except Exception:
            return block
        if len(raw) > self.cfg.image.max_size_mb * 1024 * 1024:
            try:
                img = Image.open(io.BytesIO(raw))
                long_edge = max(img.size)
                target = self.cfg.image.target_long_edge
                if long_edge > target:
                    ratio = target / long_edge
                    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                    img = img.resize(new_size, Image.LANCZOS)
                buf = io.BytesIO()
                fmt = "JPEG" if (src.get("media_type") or "").endswith("jpeg") else "PNG"
                img.save(buf, format=fmt, quality=85)
                block = {**block, "source": {**src, "data": base64.b64encode(buf.getvalue()).decode()}}
                log.debug(f"image resized {long_edge}->{target}")
            except Exception as e:
                log.warning(f"image resize fail: {e}")
        return block

    # === PDF / document ===
    async def _process_document(self, block: dict) -> list[dict]:
        src = block.get("source", {})
        st = src.get("type")
        if st == "text":
            return [{"type": "text", "text": src.get("data", "")}]
        try:
            data: bytes
            if st == "url":
                resp = await self._http.get(src["url"])
                resp.raise_for_status()
                data = resp.content
            elif st == "base64":
                data = base64.b64decode(src.get("data", ""))
            else:
                return [block]
        except Exception as e:
            log.warning(f"document load fail: {e}")
            return [{"type": "text", "text": "[文档加载失败]"}]

        media = (src.get("media_type") or "").lower()
        if "pdf" in media:
            return await asyncio.to_thread(self._pdf_to_blocks, data)
        # 其它格式：尝试当文本
        try:
            return [{"type": "text", "text": data.decode("utf-8", "ignore")}]
        except Exception:
            return [{"type": "text", "text": "[二进制文档无法解析]"}]

    def _pdf_to_blocks(self, data: bytes) -> list[dict]:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return [{"type": "text", "text": "[PDF 解析需要 pymupdf]"}]
        doc = fitz.open(stream=data, filetype="pdf")
        max_pages = self.cfg.pdf.max_pages
        pages = list(doc)[:max_pages]
        text_chunks: list[dict] = []
        text_chunks.append({"type": "text", "text": f"[PDF: {len(doc)} 页，处理前 {len(pages)} 页]"})
        all_text = []
        for i, p in enumerate(pages):
            all_text.append(f"--- Page {i+1} ---\n{p.get_text()}")
        text_chunks.append({"type": "text", "text": "\n".join(all_text)})

        if self.cfg.pdf.strategy in ("text_and_images", "images_only") and \
           len(pages) <= self.cfg.pdf.image_pages_threshold:
            for i, p in enumerate(pages):
                try:
                    pix = p.get_pixmap(dpi=120)
                    png = pix.tobytes("png")
                    text_chunks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.b64encode(png).decode(),
                        },
                    })
                except Exception as e:
                    log.warning(f"pdf page {i} render fail: {e}")
        return text_chunks
