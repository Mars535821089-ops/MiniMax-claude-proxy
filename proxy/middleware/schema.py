"""中间件 #3: tool_use schema 简化与响应还原。

问题：第三方对复杂 JSON Schema 支持差（$ref/oneOf/anyOf/嵌套深 object）。
策略：
1. 请求阶段：递归展开 $ref、把 oneOf/anyOf 拍平为带枚举说明的字段。
2. 记录"变换路径"到 ctx['schema_transforms']。
3. 响应阶段：拿到 tool_use.input 后按变换路径反向重组嵌套结构。
"""
from __future__ import annotations
import copy
from typing import Any
from ..config import SchemaCfg
from ..utils.logging import get_logger

log = get_logger("schema")


class SchemaShim:
    def __init__(self, cfg: SchemaCfg):
        self.cfg = cfg

    def preprocess_request(self, payload: dict) -> tuple[dict, dict]:
        """简化 tools[*].input_schema。"""
        ctx: dict[str, dict] = {"tool_originals": {}}
        if not self.cfg.enabled:
            return payload, ctx
        tools = payload.get("tools")
        if not tools:
            return payload, ctx
        new_tools = []
        for t in tools:
            t = copy.deepcopy(t)
            schema = t.get("input_schema")
            if isinstance(schema, dict):
                ctx["tool_originals"][t.get("name", "")] = copy.deepcopy(schema)
                t["input_schema"] = self._simplify(schema, schema, depth=0)
            new_tools.append(t)
        payload = {**payload, "tools": new_tools}
        return payload, ctx

    def _simplify(self, node: Any, root: dict, *, depth: int) -> Any:
        if depth > self.cfg.max_depth:
            return {"type": "string", "description": "(simplified: depth exceeded)"}
        if isinstance(node, dict):
            # expand $ref
            if self.cfg.expand_refs and "$ref" in node and isinstance(node["$ref"], str):
                resolved = self._resolve_ref(root, node["$ref"])
                if resolved is not None:
                    node = {**resolved, **{k: v for k, v in node.items() if k != "$ref"}}
            # flatten oneOf/anyOf — 选第一个候选，把其它候选作为 description 注释
            for key in ("oneOf", "anyOf"):
                if key in node and isinstance(node[key], list) and node[key]:
                    if (key == "oneOf" and self.cfg.flatten_oneof) or (key == "anyOf" and self.cfg.flatten_anyof):
                        first = node[key][0]
                        rest_desc = " | ".join(_describe_schema(s) for s in node[key][1:])
                        base = {k: v for k, v in node.items() if k not in ("oneOf", "anyOf")}
                        merged = {**first, **base}
                        if rest_desc:
                            desc = merged.get("description", "")
                            merged["description"] = (desc + f" (also accepts: {rest_desc})").strip()
                        node = merged
            # 递归
            out = {}
            for k, v in node.items():
                if k in ("properties", "patternProperties"):
                    out[k] = {pk: self._simplify(pv, root, depth=depth + 1) for pk, pv in v.items()}
                elif k == "items":
                    out[k] = self._simplify(v, root, depth=depth + 1)
                elif k == "additionalProperties" and isinstance(v, dict):
                    out[k] = self._simplify(v, root, depth=depth + 1)
                else:
                    out[k] = v
            return out
        if isinstance(node, list):
            return [self._simplify(x, root, depth=depth) for x in node]
        return node

    @staticmethod
    def _resolve_ref(root: dict, ref: str) -> dict | None:
        if not ref.startswith("#/"):
            return None
        cur: Any = root
        for part in ref[2:].split("/"):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur if isinstance(cur, dict) else None

    # === 响应还原 ===
    def postprocess_response(self, response: dict, ctx: dict) -> dict:
        if not (self.cfg.enabled and self.cfg.reconcile_response):
            return response
        originals = ctx.get("tool_originals", {})
        if not originals:
            return response
        for block in response.get("content", []):
            if block.get("type") != "tool_use":
                continue
            schema = originals.get(block.get("name", ""))
            if not schema:
                continue
            block["input"] = self._reconcile(block.get("input", {}), schema)
        return response

    def _reconcile(self, value: Any, schema: dict) -> Any:
        """简单还原：当模型把字符串塞给本应是 object 的字段时，尝试 JSON 解析。"""
        if not isinstance(schema, dict):
            return value
        expected = schema.get("type")
        if expected == "object" and isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except Exception:
                return value
        if expected == "array" and isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except Exception:
                return [value]
        if expected == "object" and isinstance(value, dict):
            props = schema.get("properties", {})
            return {k: self._reconcile(v, props.get(k, {})) for k, v in value.items()}
        if expected == "array" and isinstance(value, list):
            item_schema = schema.get("items", {})
            return [self._reconcile(x, item_schema) for x in value]
        return value


def _describe_schema(s: dict) -> str:
    if not isinstance(s, dict):
        return str(s)
    t = s.get("type", "any")
    if t == "object":
        keys = list((s.get("properties") or {}).keys())
        return f"object[{','.join(keys[:4])}{'...' if len(keys) > 4 else ''}]"
    if t == "array":
        return f"array[{_describe_schema(s.get('items', {}))}]"
    return str(t)
