#!/bin/bash
# ============================================================================
# LiveTalking 依赖安装脚本
# ============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}  LiveTalking 依赖安装脚本${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

echo -e "检测到 Python 版本: ${YELLOW}$PYTHON_VERSION${NC}"

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "${RED}错误: 需要 Python 3.10 或更高版本${NC}"
    exit 1
fi

# 创建虚拟环境（如果不存在）
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}创建虚拟环境: $VENV_DIR${NC}"
    python3 -m venv "$VENV_DIR"
fi

# 激活虚拟环境
echo -e "${GREEN}激活虚拟环境${NC}"
source "$VENV_DIR/bin/activate"

# 升级 pip
echo -e "${YELLOW}升级 pip...${NC}"
pip install --upgrade pip setuptools wheel > /dev/null 2>&1

# 检查 CUDA
if command -v nvcc &> /dev/null; then
    CUDA_VERSION=$(nvcc --version | grep "release" | awk '{print $5}' | sed 's/,//')
    echo -e "${GREEN}检测到 CUDA $CUDA_VERSION${NC}"
    CUDA_AVAILABLE=true
else
    echo -e "${YELLOW}未检测到 CUDA，将安装 CPU 版本的 PyTorch${NC}"
    CUDA_AVAILABLE=false
fi

# 安装 PyTorch
echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}安装 PyTorch...${NC}"
echo -e "${GREEN}=================================================${NC}"

if [ "$CUDA_AVAILABLE" = true ]; then
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
else
    pip install torch torchvision torchaudio
fi

# 安装其他依赖
echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}安装项目依赖...${NC}"
echo -e "${GREEN}=================================================${NC}"

if [ -f "$PROJECT_ROOT/requirements_full.txt" ]; then
    pip install -r "$PROJECT_ROOT/requirements_full.txt"
else
    echo -e "${RED}错误: requirements_full.txt 不存在${NC}"
    exit 1
fi

# 验证关键依赖
echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}验证关键依赖...${NC}"
echo -e "${GREEN}=================================================${NC}"

check_import() {
    module_name=$1
    if python3 -c "import $module_name" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $module_name"
        return 0
    else
        echo -e "  ${RED}✗${NC} $module_name ${RED}(缺失)${NC}"
        return 1
    fi
}

FAILED=0

echo "检查核心依赖:"
check_import "torch" || FAILED=1
check_import "av" || FAILED=1
check_import "aiortc" || FAILED=1
check_import "pydub" || FAILED=1
check_import "httpx" || FAILED=1
check_import "aiohttp" || FAILED=1
check_import "transformers" || FAILED=1
check_import "edge_tts" || FAILED=1
check_import "openai" || FAILED=1
check_import "socksio" || FAILED=1

echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}检查外部工具...${NC}"
echo -e "${GREEN}=================================================${NC}"

check_command() {
    if command -v $1 &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "  ${YELLOW}⚠${NC} $1 ${YELLOW}(未安装，可能需要)${NC}"
        return 1
    fi
}

check_command "ffmpeg"
check_command "ffprobe"

echo ""
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}=================================================${NC}"
    echo -e "${GREEN}所有依赖安装完成！${NC}"
    echo -e "${GREEN}=================================================${NC}"
    echo ""
    echo "激活虚拟环境:"
    echo "  source $VENV_DIR/bin/activate"
    echo ""
    echo "运行服务:"
    echo "  python src/main/app.py --model wav2lip --tts doubao"
else
    echo -e "${RED}=================================================${NC}"
    echo -e "${RED}部分依赖安装失败，请检查错误信息${NC}"
    echo -e "${RED}=================================================${NC}"
    exit 1
fi
