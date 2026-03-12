#!/bin/bash
###############################################################################
# LiveTalking Frontend Deployment Script
# 前端 Docker 部署脚本
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}"
    echo "=========================================="
    echo "  $1"
    echo "=========================================="
    echo -e "${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend/desktop_app"

###############################################################################
# 功能函数
###############################################################################

# 检查 Docker
check_docker() {
    print_header "检查 Docker 环境"

    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装"
        print_info "请先安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    print_success "Docker 已安装: $(docker --version)"

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose 未安装"
        exit 1
    fi

    # 检测 docker compose 命令
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi

    print_success "Docker Compose 已安装"
    echo ""
}

# 构建前端镜像
build_image() {
    print_header "构建前端镜像"

    cd "$SCRIPT_DIR"

    print_info "开始构建..."
    $DOCKER_COMPOSE build

    print_success "镜像构建完成"
    echo ""
}

# 启动服务
start_service() {
    print_header "启动前端服务"

    cd "$SCRIPT_DIR"

    print_info "启动容器..."
    $DOCKER_COMPOSE up -d

    print_success "服务已启动"
    echo ""

    show_service_info
}

# 停止服务
stop_service() {
    print_header "停止前端服务"

    cd "$SCRIPT_DIR"

    print_info "停止容器..."
    $DOCKER_COMPOSE down

    print_success "服务已停止"
    echo ""
}

# 重启服务
restart_service() {
    stop_service
    sleep 2
    start_service
}

# 查看服务状态
status_service() {
    print_header "前端服务状态"

    cd "$SCRIPT_DIR"

    $DOCKER_COMPOSE ps
    echo ""

    # 检查服务是否运行
    if docker ps | grep -q "livetalking-frontend"; then
        print_success "服务正在运行"

        # 显示日志（最近20行）
        echo ""
        print_info "最近日志:"
        $DOCKER_COMPOSE logs --tail=20
    else
        print_warning "服务未运行"
    fi

    echo ""
}

# 查看日志
view_logs() {
    local lines=${1:-50}
    cd "$SCRIPT_DIR"
    $DOCKER_COMPOSE logs --tail=$lines -f
}

# 进入容器
shell_service() {
    cd "$SCRIPT_DIR"
    print_info "进入容器 shell (输入 exit 退出)..."
    $DOCKER_COMPOSE exec livetalking-frontend sh
}

# 清理资源
clean_resources() {
    print_header "清理 Docker 资源"

    cd "$SCRIPT_DIR"

    read -p "确认清理所有相关资源? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "已取消"
        return
    fi

    print_info "停止并删除容器..."
    $DOCKER_COMPOSE down -v

    print_info "删除镜像..."
    docker rmi livetalking-frontend 2>/dev/null || true

    print_success "清理完成"
    echo ""
}

# 显示服务信息
show_service_info() {
    cat << EOF
${GREEN}前端服务已启动！${NC}

${BLUE}访问地址:${NC}
  本地访问: http://localhost:1420
  网络访问: http://$(hostname -I | awk '{print $1}'):1420

${BLUE}管理命令:${NC}
  查看状态: $0 status
  查看日志: $0 logs
  停止服务: $0 stop
  重启服务: $0 restart
  进入容器: $0 shell

${BLUE}注意事项:${NC}
  1. 确保后端服务已启动 (端口 8010)
  2. 前端通过 Vite proxy 连接后端
  3. 如遇连接问题，检查网络配置

EOF
}

###############################################################################
# 主程序
###############################################################################

show_usage() {
    cat << EOF
用法: $0 {build|start|stop|restart|status|logs|shell|clean}

命令:
  build   - 构建前端镜像
  start   - 启动服务
  stop    - 停止服务
  restart - 重启服务
  status  - 查看服务状态和日志
  logs    - 实时查看日志
  shell   - 进入容器 shell
  clean   - 清理所有 Docker 资源

不加参数运行将执行完整部署流程
EOF
}

# 完整部署
full_deploy() {
    print_header "部署 LiveTalking 前端"
    echo ""

    check_docker
    build_image
    start_service
}

# 主逻辑
case "${1:-deploy}" in
    build)
        check_docker
        build_image
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        status_service
        ;;
    logs)
        view_logs "${2:-50}"
        ;;
    shell)
        shell_service
        ;;
    clean)
        clean_resources
        ;;
    deploy)
        full_deploy
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        print_error "未知命令: $1"
        show_usage
        exit 1
        ;;
esac
