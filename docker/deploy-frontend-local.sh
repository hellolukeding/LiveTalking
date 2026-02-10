#!/bin/bash
# LiveTalking 前端部署脚本（使用本地打包文件）
# ================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $message"
}

print_message "$BLUE" "======================================"
print_message "$BLUE" "🚀 LiveTalking 前端部署"
print_message "$BLUE" "======================================"

# 检查frontend-dist目录
if [ ! -d "frontend-dist" ]; then
    print_message "$RED" "❌ frontend-dist目录不存在"
    print_message "$YELLOW" "请先在本地运行构建脚本并上传:"
    print_message "$YELLOW" "   ./build-frontend-local.sh"
    print_message "$YELLOW_ "   scp -r docker/frontend-dist root@your-server:/opt/lt/docker/"
    exit 1
fi

# 检查dist文件
if [ ! -d "frontend-dist/dist" ]; then
    print_message "$RED" "❌ frontend-dist/dist目录不存在"
    print_message "$YELLOW" "请确保本地构建成功"
    exit 1
fi

print_message "$GREEN" "✅ 找到前端打包文件"

# 显示构建信息
if [ -f "frontend-dist/build-info.txt" ]; then
    print_message "$BLUE" "📋 构建信息:"
    cat frontend-dist/build-info.txt | sed 's/^/   /'
fi

# 计算文件大小
DIST_SIZE=$(du -sh frontend-dist/dist | cut -f1)
print_message "$BLUE" "📦 打包文件大小: $DIST_SIZE"

# 修改docker-compose.yml使用本地构建文件
print_message "$BLUE" "📝 更新docker-compose.yml配置..."

# 备份原配置
if [ -f "docker-compose.yml" ] && ! grep -q "Dockerfile.frontend.local" docker-compose.yml; then
    cp docker-compose.yml docker-compose.yml.bak
    print_message "$BLUE" "💾 已备份原配置为 docker-compose.yml.bak"
fi

# 更新docker-compose.yml中的frontend配置
sed -i 's|dockerfile: docker/Dockerfile.frontend|dockerfile: docker/Dockerfile.frontend.local|' docker-compose.yml

print_message "$GREEN" "✅ 配置已更新"

# 构建前端镜像
print_message "$BLUE" "🏗️  构建前端镜像..."
docker-compose build frontend

if [ $? -eq 0 ]; then
    print_message "$GREEN" "✅ 前端镜像构建成功"

    # 询问是否启动服务
    echo ""
    printf "是否现在启动前端服务？(y/n) "
    read REPLY
    echo
    case "$REPLY" in
        [Yy]|[Yy][Ee][Ss])
            print_message "$BLUE" "🚀 启动前端服务..."
            docker-compose up -d frontend

            print_message "$GREEN" "✅ 前端服务已启动"
            print_message "$BLUE" "📊 查看状态: docker-compose ps"
            print_message "$BLUE" "📋 查看日志: docker-compose logs -f frontend"
            ;;
    esac
else
    print_message "$RED" "❌ 前端镜像构建失败"
    exit 1
fi

# 恢复原配置（可选）
print_message "$BLUE" "💡 提示：原配置已备份为 docker-compose.yml.bak"
print_message "$BLUE" "   如需恢复: cp docker-compose.yml.bak docker-compose.yml"
