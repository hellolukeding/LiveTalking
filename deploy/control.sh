#!/bin/bash
###############################################################################
# LiveTalking Service Control
# 简化的服务控制脚本
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_SCRIPT="$SCRIPT_DIR/backend.sh"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
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

# 显示菜单
show_menu() {
    clear
    echo "=========================================="
    echo "      LiveTalking 服务控制面板"
    echo "=========================================="
    echo ""
    echo "  1. 启动服务"
    echo "  2. 停止服务"
    echo "  3. 重启服务"
    echo "  4. 查看状态"
    echo "  5. 查看日志"
    echo "  6. 实时日志"
    echo "  7. 配置管理"
    echo "  0. 退出"
    echo ""
    echo "=========================================="
}

# 配置管理
config_menu() {
    echo ""
    echo "=========================================="
    echo "      配置管理"
    echo "=========================================="
    echo ""
    echo "  1. 编辑配置文件"
    echo "  2. 查看当前配置"
    echo "  3. 重置为默认配置"
    echo "  0. 返回"
    echo ""
    read -p "请选择 [0-3]: " choice

    case $choice in
        1)
            if [ -f "$SCRIPT_DIR/livetalking.conf" ]; then
                ${EDITOR:-nano} "$SCRIPT_DIR/livetalking.conf"
            else
                print_warning "配置文件不存在，将从模板创建..."
                cp "$SCRIPT_DIR/livetalking.conf.template" "$SCRIPT_DIR/livetalking.conf"
                ${EDITOR:-nano} "$SCRIPT_DIR/livetalking.conf"
            fi
            ;;
        2)
            if [ -f "$SCRIPT_DIR/livetalking.conf" ]; then
                echo ""
                cat "$SCRIPT_DIR/livetalking.conf"
            else
                print_error "配置文件不存在"
            fi
            ;;
        3)
            read -p "确认重置配置？[y/N]: " confirm
            if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
                cp "$SCRIPT_DIR/livetalking.conf.template" "$SCRIPT_DIR/livetalking.conf"
                print_success "配置已重置"
            fi
            ;;
        0)
            return
            ;;
        *)
            print_error "无效选择"
            ;;
    esac

    read -p "按回车键继续..."
}

# 主循环
main_loop() {
    while true; do
        show_menu
        read -p "请选择 [0-7]: " choice

        case $choice in
            1)
                print_info "启动服务..."
                $BACKEND_SCRIPT start
                read -p "按回车键继续..."
                ;;
            2)
                print_info "停止服务..."
                $BACKEND_SCRIPT stop
                read -p "按回车键继续..."
                ;;
            3)
                print_info "重启服务..."
                $BACKEND_SCRIPT restart
                read -p "按回车键继续..."
                ;;
            4)
                $BACKEND_SCRIPT status
                read -p "按回车键继续..."
                ;;
            5)
                read -p "显示最近多少行日志? [50]: " lines
                $BACKEND_SCRIPT logs ${lines:-50}
                read -p "按回车键继续..."
                ;;
            6)
                print_info "实时日志模式 (按 Ctrl+C 退出)"
                $BACKEND_SCRIPT follow
                ;;
            7)
                config_menu
                ;;
            0)
                print_info "退出"
                exit 0
                ;;
            *)
                print_error "无效选择"
                read -p "按回车键继续..."
                ;;
        esac
    done
}

# 命令行模式
if [ $# -gt 0 ]; then
    $BACKEND_SCRIPT "$@"
else
    main_loop
fi
