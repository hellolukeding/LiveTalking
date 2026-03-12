#!/bin/bash
# ============================================================================
# 快速修复缺失的依赖
# ============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

echo -e "${GREEN}快速修复缺失依赖...${NC}\n"

# 激活虚拟环境
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo -e "${RED}错误: 虚拟环境不存在，请先运行 install_deps.sh${NC}"
    exit 1
fi

# 常见缺失的依赖
MISSING_DEPS=(
    "pydub"
    "socksio"
    "httpx"
    "websocket-client"
    "aiohttp"
    "av"
)

echo "安装常见缺失的依赖..."
for dep in "${MISSING_DEPS[@]}"; do
    echo -e "  ${YELLOW}安装 $dep...${NC}"
    pip install "$dep" -q
done

echo ""
echo -e "${GREEN}完成！运行以下命令验证依赖:${NC}"
echo -e "  ${YELLOW}python scripts/check_deps.py${NC}"
