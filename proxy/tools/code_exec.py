"""本地实现的 Anthropic server-side code_execution 工具。

简单的 subprocess 沙箱：
- 限制超时
- 限制内存（仅 Unix，setrlimit）
- 临时目录隔离
- 仅允许 Python（最常见场景）

⚠️ 真要做严格隔离请改成 docker / firecracker 后端。
"""
from __future__ import annotations
import asyncio
import os
import resource
import shutil
import sys
import tempfile
from pathlib import Path
from ..config import CodeExecCfg
from ..utils.logging import get_logger

log = get_logger("code_exec")


async def execute_code(
    code: str,
    *,
    cfg: CodeExecCfg,
    language: str = "python",
) -> dict:
    if cfg.backend == "subprocess":
        return await _subprocess(code, cfg, language)
    if cfg.backend == "docker":
        return await _docker(code, cfg, language)
    return {"stdout": "", "stderr": f"backend {cfg.backend} not implemented", "exit_code": -1}


async def _subprocess(code: str, cfg: CodeExecCfg, language: str) -> dict:
    if language not in ("python", "bash", "sh"):
        return {"stdout": "", "stderr": f"unsupported language: {language}", "exit_code": -1}

    workdir = Path(tempfile.mkdtemp(prefix="MiniMax_exec_"))
    try:
        if language == "python":
            script = workdir / "main.py"
            script.write_text(code, encoding="utf-8")
            cmd = [sys.executable, str(script)]
        else:
            script = workdir / "main.sh"
            script.write_text(code, encoding="utf-8")
            cmd = ["bash", str(script)]

        def _preexec():
            try:
                mem_bytes = cfg.memory_limit_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except Exception:
                pass

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workdir),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                preexec_fn=_preexec if sys.platform != "win32" else None,
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=cfg.timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return {"stdout": "", "stderr": f"TIMEOUT after {cfg.timeout}s", "exit_code": -1}
            return {
                "stdout": out.decode("utf-8", "ignore")[-50000:],
                "stderr": err.decode("utf-8", "ignore")[-20000:],
                "exit_code": proc.returncode,
            }
        except Exception as e:
            return {"stdout": "", "stderr": f"exec error: {e!r}", "exit_code": -1}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def _docker(code: str, cfg: CodeExecCfg, language: str) -> dict:
    # 占位：可对接 docker python image
    return {"stdout": "", "stderr": "docker backend not yet wired", "exit_code": -1}
