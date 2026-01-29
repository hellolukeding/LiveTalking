#!/bin/bash
# LiveTalking Docker 一键部署脚本
# =========================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目路径
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_DIR="$PROJECT_DIR/docker"

# 打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $message"
}

# 检查 Docker 和 Docker Compose
check_requirements() {
    print_message "$BLUE" "检查系统依赖..."

    if ! command -v docker &> /dev/null; then
        print_message "$RED" "❌ Docker 未安装，请先安装 Docker"
        exit 1
    fi

    if ! command -v docker compose &> /dev/null; then
        print_message "$RED" "❌ Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi

    # 检查 NVIDIA Docker (GPU 支持)
    if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        print_message "$GREEN" "✅ NVIDIA Docker 支持"
        HAS_GPU=true
    else
        print_message "$YELLOW" "⚠️  未检测到 NVIDIA GPU 支持，将使用 CPU 模式"
        HAS_GPU=false
    fi

    print_message "$GREEN" "✅ 系统依赖检查完成"
}

# 创建必要的目录
create_directories() {
    print_message "$BLUE" "创建必要的目录..."

    mkdir -p "$DOCKER_DIR/logs"
    mkdir -p "$PROJECT_DIR/models"
    mkdir -p "$PROJECT_DIR/data"
    mkdir -p "$PROJECT_DIR/assets"

    print_message "$GREEN" "✅ 目录创建完成"
}

# 检查环境变量文件
check_env_file() {
    print_message "$BLUE" "检查环境变量配置..."

    if [ ! -f "$PROJECT_DIR/.env" ]; then
        print_message "$YELLOW" "⚠️  未找到 .env 文件，使用默认配置"
        cat > "$PROJECT_DIR/.env" << 'EOF'
# LiveTalking Docker 环境配置

# LLM 配置
LLM_MODEL=gpt-3.5-turbo
OPEN_AI_URL=https://api.openai.com/v1
OPEN_AI_API_KEY=your-api-key-here

# TTS 配置
TTS_TYPE=edge
EDGE_TTS_VOICE=zh-CN-YunxiNeural

# ASR 配置
ASR_TYPE=lip

# 服务配置
LISTEN_PORT=8010
MAX_SESSION=5
FPS=25
LOG_LEVEL=INFO
EOF
        print_message "$GREEN" "✅ 已创建默认 .env 文件"
        print_message "$YELLOW" "⚠️  请编辑 .env 文件配置您的 API 密钥"
    else
        print_message "$GREEN" "✅ .env 文件已存在"
    fi
}

# 构建镜像
build_images() {
    print_message "$BLUE" "构建 Docker 镜像..."
    print_message "$YELLOW" "这可能需要几分钟时间..."

    cd "$DOCKER_DIR"

    # 构建后端镜像
    print_message "$BLUE" "构建后端镜像..."
    if docker compose build backend; then
        print_message "$GREEN" "✅ 后端镜像构建成功"
    else
        print_message "$RED" "❌ 后端镜像构建失败"
        exit 1
    fi

    # 构建前端镜像
    print_message "$BLUE" "构建前端镜像..."
    if docker compose build frontend; then
        print_message "$GREEN" "✅ 前端镜像构建成功"
    else
        print_message "$RED" "❌ 前端镜像构建失败"
        exit 1
    fi

    print_message "$GREEN" "✅ 所有镜像构建完成"
}

# 启动服务
start_services() {
    print_message "$BLUE" "启动服务..."

    cd "$DOCKER_DIR"

    # 启动所有服务
    if docker compose up -d; then
        print_message "$GREEN" "✅ 服务启动成功"
    else
        print_message "$RED" "❌ 服务启动失败"
        exit 1
    fi

    # 等待服务就绪
    print_message "$BLUE" "等待服务就绪..."
    sleep 10
}

# 显示服务状态
show_status() {
    print_message "$BLUE" "服务状态:"
    echo ""
    docker compose ps
    echo ""
}

# 显示访问信息
show_access_info() {
    print_message "$GREEN" "========================================="
    print_message "$GREEN" "🎉 LiveTalking 部署成功！"
    print_message "$GREEN" "========================================="
    echo ""
    print_message "$BLUE" "📱 访问地址:"
    print_message "$NC" "   前端应用: http://localhost"
    print_message "$NC" "   后端 API: http://localhost:8010"
    print_message "$NC" "   SRS 控制台: http://localhost:8080/console/"
    print_message "$NC" "   FLV 播放: http://localhost:8080/live/livestream.flv"
    echo ""
    print_message "$BLUE" "🔧 管理命令:"
    print_message "$NC" "   查看日志: docker compose -f docker/docker-compose.yml logs -f"
    print_message "$NC" "   停止服务: docker compose -f docker/docker-compose.yml down"
    print_message "$NC" "   重启服务: docker compose -f docker/docker-compose.yml restart"
    print_message "$NC" "   查看状态: docker compose -f docker/docker-compose.yml ps"
    echo ""
    print_message "$YELLOW" "⚠️  注意事项:"
    print_message "$NC" "   1. 首次运行可能需要下载模型文件"
    print_message "$NC" "   2. 请确保已在 .env 中配置正确的 API 密钥"
    print_message "$NC" "   3. GPU 服务器需要 NVIDIA Docker 支持"
    echo ""
}

# 清理旧容器和镜像
cleanup() {
    print_message "$YELLOW" "是否清理旧的容器和镜像? (y/N)"
    read -r response

    if [[ "$response" =~ ^[Yy]$ ]]; then
        print_message "$BLUE" "清理旧资源..."
        cd "$DOCKER_DIR"
        docker compose down -v --remove-orphans
        docker system prune -f
        print_message "$GREEN" "✅ 清理完成"
    fi
}

# 显示帮助信息
show_help() {
    echo "LiveTalking Docker 部署脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --build-only    仅构建镜像"
    echo "  --start-only    仅启动服务"
    echo "  --cleanup       清理旧容器和镜像"
    echo "  --help          显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0              # 完整部署（推荐）"
    echo "  $0 --build-only # 仅构建镜像"
    echo "  $0 --start-only # 仅启动服务"
}

# 主函数
main() {
    print_message "$BLUE" "========================================="
    print_message "$BLUE" "🚀 LiveTalking Docker 部署"
    print_message "$BLUE" "========================================="
    echo ""

    # 处理命令行参数
    case "${1:-}" in
        --build-only)
            check_requirements
            create_directories
            build_images
            exit 0
            ;;
        --start-only)
            start_services
            show_status
            show_access_info
            exit 0
            ;;
        --cleanup)
            cleanup
            exit 0
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            # 完整部署流程
            check_requirements
            create_directories
            check_env_file

            # 询问是否清理
            if [ -f "$DOCKER_DIR/docker-compose.yml" ]; then
                cleanup
            fi

            build_images
            start_services
            show_status
            show_access_info
            ;;
    esac
}

# 运行主函数
main "$@"
