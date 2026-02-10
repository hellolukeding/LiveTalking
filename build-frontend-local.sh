#!/bin/bash
# LiveTalking 前端本地打包脚本
# =====================================

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $message"
}

# 项目目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$PROJECT_DIR/frontend/desktop_app"
DIST_DIR="$PROJECT_DIR/docker/frontend-dist"

print_message "$BLUE" "======================================"
print_message "$BLUE" "🏗️  LiveTalking 前端本地打包"
print_message "$BLUE" "======================================"

# 配置后端API地址（默认值）
BACKEND_API_URL="${1:-http://localhost:8010}"

print_message "$BLUE" "📝 配置信息:"
print_message "$BLUE" "   后端API地址: $BACKEND_API_URL"
echo ""

# 如果使用默认值，提示用户可以自定义
if [ "$1" = "" ]; then
    print_message "$YELLOW" "💡 提示：使用默认API地址"
    print_message "$YELLOW" "   自定义API地址: $0 <API_URL>"
    print_message "$YELLOW" "   示例: $0 http://192.168.1.100:8010"
    echo ""
fi

# 检查前端目录
if [ ! -d "$FRONTEND_DIR" ]; then
    print_message "$RED" "❌ 前端目录不存在: $FRONTEND_DIR"
    exit 1
fi

cd "$FRONTEND_DIR"

# 检查yarn是否安装
if ! command -v yarn &> /dev/null; then
    print_message "$YELLOW" "⚠️  yarn未安装，使用npm代替"
    PACKAGE_MANAGER="npm"
else
    PACKAGE_MANAGER="yarn"
fi

print_message "$BLUE" "📦 使用包管理器: $PACKAGE_MANAGER"

# 清理旧的构建
print_message "$BLUE" "🧹 清理旧的构建文件..."
rm -rf dist node_modules/.vite

# 安装依赖（如果需要）
if [ ! -d "node_modules" ]; then
    print_message "$BLUE" "📥 安装依赖..."
    if [ "$PACKAGE_MANAGER" = "yarn" ]; then
        yarn install
    else
        npm install
    fi
fi

# 构建前端（传入API地址）
print_message "$BLUE" "🔨 构建前端应用..."
if [ "$PACKAGE_MANAGER" = "yarn" ]; then
    VITE_API_URL="$BACKEND_API_URL" yarn build
else
    VITE_API_URL="$BACKEND_API_URL" npm run build
fi

# 检查构建结果
if [ ! -d "dist" ]; then
    print_message "$RED" "❌ 构建失败，dist目录不存在"
    exit 1
fi

# 创建输出目录
print_message "$BLUE" "📁 准备部署文件..."
mkdir -p "$DIST_DIR"

# 复制构建文件到docker目录
print_message "$BLUE" "📋 复制构建文件..."
cp -r dist "$DIST_DIR/"

# 创建部署信息文件
cat > "$DIST_DIR/build-info.txt" << EOF
构建时间: $(date '+%Y-%m-%d %H:%M:%S')
构建主机: $(hostname)
构建用户: $(whoami)
Git Commit: $(cd "$PROJECT_DIR" && git rev-parse --short HEAD 2>/dev/null || echo "N/A")
后端API: $BACKEND_API_URL
EOF

# 计算文件大小
DIST_SIZE=$(du -sh "$DIST_DIR/dist" | cut -f1)
print_message "$GREEN" "✅ 构建成功！"
print_message "$GREEN" "   打包文件: $DIST_DIR/dist"
print_message "$GREEN" "   文件大小: $DIST_SIZE"
print_message "$GREEN" "   构建信息: $DIST_DIR/build-info.txt"

echo ""
print_message "$BLUE" "📤 下一步："
print_message "$BLUE" "   1. 上传部署包到服务器:"
print_message "$BLUE" "      scp -r docker/frontend-dist root@your-server:/opt/lt/docker/"
print_message "$BLUE" "   2. 在服务器上运行部署脚本:"
print_message "$BLUE" "      cd /opt/lt/docker && ./deploy-frontend-local.sh"

# 显示目录结构
echo ""
print_message "$BLUE" "📂 部署包结构:"
ls -lh "$DIST_DIR/"
