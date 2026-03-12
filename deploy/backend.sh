#!/bin/bash
###############################################################################
# LiveTalking Backend Control Script
# 用于启动、停止、重启和查看后端服务状态
###############################################################################

set -e

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 加载配置文件
if [ -f "$SCRIPT_DIR/livetalking.conf" ]; then
    source "$SCRIPT_DIR/livetalking.conf"
else
    # 默认配置
    PROJECT_ROOT="/opt/2026/LiveTalking"
    VENV_PATH="$PROJECT_ROOT/.venv"
    PYTHON_BIN="$VENV_PATH/bin/python"
    LOG_DIR="$PROJECT_ROOT/logs"
    PID_FILE="$PROJECT_ROOT/livetalking.pid"
    LISTEN_PORT=8010
    MODEL_TYPE="wav2lip"
    AVATAR_ID="wav2lip256_avatar1"
    MAX_SESSION=1
    TTS_TYPE="doubao"
    ASR_TYPE="lip"
    VIDEO_BITRATE=5000
    VIDEO_CODEC="auto"
fi

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 服务名称
SERVICE_NAME="livetalking-backend"

# 日志文件
MAIN_LOG="$LOG_DIR/livetalking.log"
ERROR_LOG="$LOG_DIR/error.log"

###############################################################################
# 辅助函数
###############################################################################

# 获取 PID
get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    fi
}

# 检查服务是否运行
is_running() {
    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        ps -p "$pid" > /dev/null 2>&1
        return $?
    fi
    return 1
}

# 等待服务启动
wait_for_service() {
    local max_wait=60
    local waited=0
    echo -n "等待服务启动..."
    while [ $waited -lt $max_wait ]; do
        if is_running; then
            echo " 已启动 (PID: $(get_pid))"
            return 0
        fi
        sleep 1
        echo -n "."
        ((waited++))
    done
    echo " 启动超时"
    return 1
}

# 检查端口是否被占用
check_port() {
    if netstat -tuln 2>/dev/null | grep -q ":$LISTEN_PORT "; then
        echo "警告: 端口 $LISTEN_PORT 已被占用"
        return 1
    fi
    return 0
}

###############################################################################
# 服务操作
###############################################################################

# 启动服务
start_service() {
    if is_running; then
        echo "服务已在运行中 (PID: $(get_pid))"
        return 0
    fi

    echo "启动 LiveTalking 后端服务..."

    # 检查虚拟环境
    if [ ! -f "$PYTHON_BIN" ]; then
        echo "错误: Python 虚拟环境不存在: $VENV_PATH"
        echo "请先运行: python -m venv $VENV_PATH && pip install -r requirements_full.txt"
        return 1
    fi

    # 检查配置
    if [ ! -f "$PROJECT_ROOT/src/main/app.py" ]; then
        echo "错误: 找不到 app.py，请确认项目路径正确"
        return 1
    fi

    # 构建启动命令
    cd "$PROJECT_ROOT"
    local cmd="$PYTHON_BIN src/main/app.py"
    cmd="$cmd --model $MODEL_TYPE"
    cmd="$cmd --tts $TTS_TYPE"
    cmd="$cmd --avatar_id $AVATAR_ID"
    cmd="$cmd --max_session $MAX_SESSION"
    cmd="$cmd --listenport $LISTEN_PORT"
    cmd="$cmd --video_bitrate $VIDEO_BITRATE"
    cmd="$cmd --video_codec $VIDEO_CODEC"

    if [ -n "$ASR_TYPE" ]; then
        cmd="$cmd --asr $ASR_TYPE"
    fi

    echo "启动命令: $cmd"
    echo "日志文件: $MAIN_LOG"

    # 启动服务
    nohup $cmd > "$MAIN_LOG" 2>> "$ERROR_LOG" &
    local pid=$!
    echo $pid > "$PID_FILE"

    # 等待服务启动
    if wait_for_service; then
        echo ""
        echo "=========================================="
        echo "服务启动成功！"
        echo "=========================================="
        echo "  PID: $(get_pid)"
        echo "  端口: $LISTEN_PORT"
        echo "  模型: $MODEL_TYPE"
        echo "  TTS: $TTS_TYPE"
        echo ""
        echo "访问地址:"
        echo "  WebRTC API: http://localhost:$LISTEN_PORT/webrtcapi.html"
        echo "  Dashboard: http://localhost:$LISTEN_PORT/dashboard.html"
        echo "  Avatar API: http://localhost:$LISTEN_PORT/avatars"
        echo ""
        echo "查看日志: tail -f $MAIN_LOG"
        echo "=========================================="
        return 0
    else
        echo ""
        echo "错误: 服务启动失败，请查看日志:"
        echo "  tail -100 $ERROR_LOG"
        return 1
    fi
}

# 停止服务
stop_service() {
    if ! is_running; then
        echo "服务未运行"
        [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
        return 0
    fi

    local pid=$(get_pid)
    echo "停止服务 (PID: $pid)..."

    # 尝试优雅关闭
    kill "$pid" 2>/dev/null || true

    # 等待进程结束
    local count=0
    while ps -p "$pid" > /dev/null 2>&1 && [ $count -lt 30 ]; do
        sleep 1
        ((count++))
    done

    # 如果还在运行，强制终止
    if ps -p "$pid" > /dev/null 2>&1; then
        echo "强制终止..."
        kill -9 "$pid" 2>/dev/null || true
        sleep 1
    fi

    [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
    echo "服务已停止"
}

# 重启服务
restart_service() {
    stop_service
    sleep 2
    start_service
}

# 查看服务状态
status_service() {
    echo "=========================================="
    echo "LiveTalking 后端服务状态"
    echo "=========================================="

    if is_running; then
        local pid=$(get_pid)
        echo "状态: 运行中"
        echo "PID: $pid"
        echo ""
        echo "进程信息:"
        ps -p "$pid" -o pid,ppid,%mem,%cpu,cmd --no-headers | awk '{printf "  PID: %s\n  父PID: %s\n  内存: %s%%\n  CPU: %s%%\n  命令: %s\n", $1, $2, $3, $4, $5}'
        echo ""
        echo "网络监听:"
        netstat -tlnp 2>/dev/null | grep "$pid" | awk '{printf "  %s\n", $0}' || echo "  无法获取网络信息"
        echo ""
        echo "日志文件:"
        echo "  主日志: $MAIN_LOG"
        echo "  错误日志: $ERROR_LOG"
    else
        echo "状态: 未运行"
    fi

    echo "=========================================="
    return 0
}

# 查看日志
view_logs() {
    local lines=${1:-50}
    if [ -f "$MAIN_LOG" ]; then
        echo "=== 最近 $lines 行日志 ==="
        tail -n "$lines" "$MAIN_LOG"
    else
        echo "日志文件不存在: $MAIN_LOG"
    fi
}

# 实时日志
follow_logs() {
    if [ -f "$MAIN_LOG" ]; then
        tail -f "$MAIN_LOG"
    else
        echo "日志文件不存在: $MAIN_LOG"
    fi
}

###############################################################################
# 主程序
###############################################################################

# 显示使用说明
show_usage() {
    cat << EOF
用法: $0 {start|stop|restart|status|logs|follow}

命令:
  start    - 启动服务
  stop     - 停止服务
  restart  - 重启服务
  status   - 查看服务状态
  logs [n] - 查看最近 n 行日志 (默认 50 行)
  follow   - 实时查看日志

配置文件: $SCRIPT_DIR/livetalking.conf
EOF
}

# 主逻辑
case "${1:-}" in
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
    follow)
        follow_logs
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

exit $?
