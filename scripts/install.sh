#!/usr/bin/env bash
# 一键安装：创建虚拟环境 + 安装依赖 + 拷贝配置 + 创建启动脚本
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
echo "📦 安装 MiniMax-claude-proxy 到 $ROOT"

# 1) venv
if [ ! -d ".venv" ]; then
  echo "→ 创建虚拟环境 .venv"
  python3 -m venv .venv
fi

# 2) 激活并安装
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

# 3) 配置文件
if [ ! -f "config.yaml" ]; then
  cp config.yaml.example config.yaml
  echo ""
  echo "⚠️  已生成 config.yaml — 请编辑并填入您的 API Key："
  echo "    $ROOT/config.yaml"
fi

# 4) 创建 systemd / launchctl 友好的启动器
mkdir -p ~/.MiniMax-claude-proxy
cat > ~/.MiniMax-claude-proxy/launch.sh <<EOF
#!/usr/bin/env bash
cd "$ROOT"
source .venv/bin/activate
exec python -m proxy.main --config "$ROOT/config.yaml"
EOF
chmod +x ~/.MiniMax-claude-proxy/launch.sh

echo ""
echo "✅ 安装完成"
echo ""
echo "下一步："
echo "  1. 编辑 $ROOT/config.yaml 填入您的真实 API Key"
echo "  2. 启动：bash scripts/start.sh"
echo "  3. 让 Claude Code 走代理（在 shell 中 export）："
echo "       export ANTHROPIC_BASE_URL=http://127.0.0.1:8787"
echo "       export ANTHROPIC_API_KEY=sk-any-value-just-not-empty"
echo "       export ANTHROPIC_MODEL=MiniMax-M3"
echo "  4. 重启 claude（claude）即可"
