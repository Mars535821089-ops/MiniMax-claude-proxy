"""抓 README 用的真实截图。

输出到 docs/screenshots/*.png，README 直接引用。

运行：.venv/bin/python scripts/capture_screenshots.py
"""
from __future__ import annotations
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

DOCS_BASE = "https://mars535821089-ops.github.io/MiniMax-claude-proxy/latest"
REPO_URL = "https://github.com/Mars535821089-ops/MiniMax-claude-proxy"

# 视口尺寸统一
VIEWPORT = {"width": 1280, "height": 800}


def shot(page, url: str, filename: str, wait_selector: str | None = None, full_page: bool = True):
    print(f"  → {url}")
    page.goto(url, wait_until="networkidle", timeout=30_000)
    if wait_selector:
        page.wait_for_selector(wait_selector, timeout=10_000)
    # 等动画/字体稳定
    page.wait_for_timeout(800)
    out = OUT / filename
    page.screenshot(path=str(out), full_page=full_page)
    print(f"    saved {out.name} ({out.stat().st_size // 1024} KB)")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        page = ctx.new_page()

        # 1) 文档站首页
        shot(page, f"{DOCS_BASE}/", "docs-home.png",
             wait_selector="article")

        # 2) 快速开始页
        shot(page, f"{DOCS_BASE}/quickstart/", "docs-quickstart.png",
             wait_selector="article")

        # 3) 架构详解页
        shot(page, f"{DOCS_BASE}/architecture/", "docs-architecture.png",
             wait_selector="article")

        # 4) GitHub 仓库主页（README 渲染图）—— GitHub 偶有 networkidle 超时
        try:
            shot(page, REPO_URL, "github-repo.png",
                 wait_selector="article", full_page=False)
        except Exception as e:
            print(f"  ⚠️  GitHub 截图跳过（反爬/networkidle）：{e.__class__.__name__}")

        browser.close()
    print(f"\n✅ {len(list(OUT.glob('*.png')))} 张截图已保存到 {OUT}/")


if __name__ == "__main__":
    main()
