#!/bin/bash
###############################################################################
# LiveTalking 本地部署脚本
# 一键部署 LiveTalking 到本机
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
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
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 配置
INSTALL_DIR="$PROJECT_ROOT"
SERVICE_NAME="livetalking-backend"
SYSTEMD_SERVICE="/etc/systemd/system/$SERVICE_NAME.service"

###############################################################################
# 部署步骤
###############################################################################

# 检查系统
check_system() {
    print_header "检查系统环境"

    # 检查操作系统
    if [ ! -f /etc/os-release ]; then
        print_error "无法检测操作系统"
        exit 1
    fi

    . /etc/os-release
    print_info "操作系统: $PRETTY_NAME"

    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        print_error "未安装 Python 3"
        print_info "请先安装 Python 3.8+"
        exit 1
    fi
    print_success "Python: $(python3 --version)"

    # 检查 pip
    if ! command -v pip3 &> /dev/null; then
        print_error "未安装 pip3"
        exit 1
    fi
    print_success "pip3 已安装"

    # 检查 venv
    python3 -m venv --help &> /dev/null
    print_success "venv 模块可用"

    echo ""
}

# 安装依赖
install_dependencies() {
    print_header "安装系统依赖"

    # 检测包管理器
    if command -v apt-get &> /dev/null; then
        PKG_MANAGER="apt-get"
        UPDATE_CMD="apt-get update -qq"
        INSTALL_CMD="apt-get install -y -qq"
    elif command -v yum &> /dev/null; then
        PKG_MANAGER="yum"
        UPDATE_CMD="yum update -y -q"
        INSTALL_CMD="yum install -y -q"
    else
        print_error "不支持的包管理器"
        exit 1
    fi

    print_info "更新软件包列表..."
    sudo $UPDATE_CMD || print_warning "更新失败，继续..."

    # 基础依赖
    local packages="ffmpeg python3-venv curl wget git"
    print_info "安装依赖: $packages"
    sudo $INSTALL_CMD $packages

    print_success "系统依赖安装完成"
    echo ""
}

# 设置虚拟环境
setup_venv() {
    print_header "设置 Python 虚拟环境"

    if [ -d "$PROJECT_ROOT/.venv" ]; then
        print_warning "虚拟环境已存在"
        read -p "是否重新创建? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "删除旧虚拟环境..."
            rm -rf "$PROJECT_ROOT/.venv"
        else
            print_info "保留现有虚拟环境"
            echo ""
            return
        fi
    fi

    print_info "创建虚拟环境..."
    python3 -m venv "$PROJECT_ROOT/.venv"

    print_info "激活虚拟环境..."
    source "$PROJECT_ROOT/.venv/bin/activate"

    print_info "升级 pip..."
    pip install --upgrade pip -q

    print_success "虚拟环境创建完成"
    echo ""
}

# 安装 Python 依赖
install_python_packages() {
    print_header "安装 Python 依赖包"

    source "$PROJECT_ROOT/.venv/bin/activate"

    # 检查依赖文件
    local req_file="$PROJECT_ROOT/requirements_full.txt"
    if [ ! -f "$req_file" ]; then
        req_file="$PROJECT_ROOT/requirements.txt"
    fi

    if [ ! -f "$req_file" ]; then
        print_error "找不到依赖文件"
        exit 1
    fi

    print_info "从 $req_file 安装依赖..."
    print_warning "这可能需要几分钟，请耐心等待..."

    pip install -r "$req_file"

    print_success "Python 依赖安装完成"
    echo ""
}

# 创建配置文件
setup_config() {
    print_header "配置服务"

    local config_file="$SCRIPT_DIR/livetalking.conf"

    if [ ! -f "$config_file" ]; then
        print_info "从模板创建配置文件..."
        cp "$SCRIPT_DIR/livetalking.conf.template" "$config_file"
        print_success "配置文件已创建: $config_file"
        print_warning "请根据实际情况编辑配置文件"
    else
        print_info "配置文件已存在"
    fi

    echo ""
}

# 设置权限
setup_permissions() {
    print_header "设置文件权限"

    # 设置脚本可执行权限
    chmod +x "$SCRIPT_DIR/backend.sh"
    chmod +x "$SCRIPT_DIR/control.sh"

    # 创建日志目录
    mkdir -p "$PROJECT_ROOT/logs"

    print_success "权限设置完成"
    echo ""
}

# 安装 systemd 服务
install_service() {
    print_header "安装 systemd 服务"

    if [ ! -f "$SCRIPT_DIR/$SERVICE_NAME.service" ]; then
        print_error "服务文件不存在"
        return 1
    fi

    # 检查是否以 root 运行
    if [ "$EUID" -ne 0 ]; then
        print_warning "需要 root 权限安装 systemd 服务"
        print_info "请使用: sudo $0 install"
        echo ""

        read -p "是否复制服务文件到 /etc/systemd/system? [y/N]: " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "跳过服务安装，可手动安装"
            echo ""
            return
        fi
    fi

    print_info "安装 systemd 服务..."

    # 复制服务文件
    sudo cp "$SCRIPT_DIR/$SERVICE_NAME.service" "$SYSTEMD_SERVICE"

    # 重新加载 systemd
    sudo systemctl daemon-reload

    # 启用开机自启
    sudo systemctl enable $SERVICE_NAME

    print_success "systemd 服务已安装"
    print_info "服务名称: $SERVICE_NAME"
    echo ""
}

# 创建快捷命令
create_shortcuts() {
    print_header "创建快捷命令"

    local bin_link="/usr/local/bin/livetalking"

    if [ "$EUID" -eq 0 ]; then
        ln -sf "$SCRIPT_DIR/control.sh" "$bin_link"
        chmod +x "$bin_link"
        print_success "快捷命令已创建: livetalking"
        print_info "使用方法: livetalking [start|stop|restart|status|logs]"
    else
        print_info "需要 root 权限创建全局命令"
        print_info "可以使用: $SCRIPT_DIR/control.sh"
    fi

    echo ""
}

# 显示部署完成信息
show_completion() {
    print_header "部署完成"

    cat << EOF
${GREEN}LiveTalking 已成功部署到本机！${NC}

${BLUE}项目目录:${NC} $PROJECT_ROOT
${BLUE}配置文件:${NC} $SCRIPT_DIR/livetalking.conf
${BLUE}日志目录:${NC} $PROJECT_ROOT/logs

${BLUE}启动服务:${NC}
  方式1 (推荐): $SCRIPT_DIR/backend.sh start
  方式2:       $SCRIPT_DIR/control.sh
  方式3:       systemctl start $SERVICE_NAME

${BLUE}管理服务:${NC}
  查看状态: $SCRIPT_DIR/backend.sh status
  查看日志: $SCRIPT_DIR/backend.sh logs
  实时日志: $SCRIPT_DIR/backend.sh follow
  停止服务: $SCRIPT_DIR/backend.sh stop
  重启服务: $SCRIPT_DIR/backend.sh restart

${BLUE}WebRTC 访问地址:${NC}
  http://localhost:8010/webrtcapi.html
  http://localhost:8010/dashboard.html

${BLUE}API 端点:${NC}
  POST /offer              - WebRTC 连接
  POST /human              - 发送消息
  GET  /avatars            - 获取形象列表
  POST /avatars            - 创建形象
  GET  /avatars/{id}       - 获取形象详情

${YELLOW}注意事项:${NC}
  1. 请根据实际情况修改配置文件
  2. 确保模型文件已下载到 models/ 目录
  3. 确保音频设备正常工作
  4. 如遇问题，请查看日志文件

EOF
}

###############################################################################
# 主程序
###############################################################################

# 显示使用说明
show_usage() {
    cat << EOF
用法: $0 [命令]

命令:
  install  - 执行完整部署
  update   - 更新 Python 依赖
  config   - 配置服务
  service  - 安装 systemd 服务
  status   - 查看部署状态

不加参数运行将执行完整部署
EOF
}

# 部署状态检查
check_status() {
    print_header "部署状态检查"

    echo "项目目录: $PROJECT_ROOT"
    echo ""

    # 虚拟环境
    if [ -d "$PROJECT_ROOT/.venv" ]; then
        print_success "Python 虚拟环境: 已安装"
        source "$PROJECT_ROOT/.venv/bin/activate"
        echo "  Python: $(python --version)"
        echo "  pip: $(pip --version)"
    else
        print_warning "Python 虚拟环境: 未安装"
    fi

    # 配置文件
    if [ -f "$SCRIPT_DIR/livetalking.conf" ]; then
        print_success "配置文件: 已创建"
    else
        print_warning "配置文件: 未创建"
    fi

    # systemd 服务
    if [ -f "$SYSTEMD_SERVICE" ]; then
        print_success "systemd 服务: 已安装"
        if systemctl is-active $SERVICE_NAME &> /dev/null; then
            echo "  状态: 运行中 (PID: $(cat $PROJECT_ROOT/livetalking.pid 2>/dev/null || echo 'N/A'))"
        else
            echo "  状态: 未运行"
        fi
    else
        print_warning "systemd 服务: 未安装"
    fi

    echo ""
}

# 更新依赖
update_dependencies() {
    print_header "更新 Python 依赖"

    if [ ! -d "$PROJECT_ROOT/.venv" ]; then
        print_error "虚拟环境不存在，请先运行: $0 install"
        exit 1
    fi

    source "$PROJECT_ROOT/.venv/bin/activate"

    print_info "更新 pip..."
    pip install --upgrade pip -q

    print_info "更新依赖包..."
    local req_file="$PROJECT_ROOT/requirements_full.txt"
    if [ ! -f "$req_file" ]; then
        req_file="$PROJECT_ROOT/requirements.txt"
    fi
    pip install -r "$req_file" --upgrade

    print_success "依赖更新完成"
    echo ""
}

# 完整部署
full_install() {
    print_header "开始部署 LiveTalking"
    echo ""

    check_system
    install_dependencies
    setup_venv
    install_python_packages
    setup_config
    setup_permissions
    install_service
    create_shortcuts
    show_completion

    # 询问是否启动服务
    echo ""
    read -p "是否现在启动服务? [Y/n]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        "$SCRIPT_DIR/backend.sh" start
    fi
}

# 主逻辑
case "${1:-install}" in
    install)
        full_install
        ;;
    update)
        update_dependencies
        ;;
    config)
        setup_config
        if [ -f "$SCRIPT_DIR/livetalking.conf" ]; then
            ${EDITOR:-nano} "$SCRIPT_DIR/livetalking.conf"
        fi
        ;;
    service)
        install_service
        create_shortcuts
        ;;
    status)
        check_status
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
