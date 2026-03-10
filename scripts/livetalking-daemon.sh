#!/bin/bash
# LiveTalking 服务管理脚本
# =========================================

PROJECT_DIR="/opt/2026/LiveTalking"
PID_FILE="$PROJECT_DIR/livetalking.pid"
LOG_FILE="$PROJECT_DIR/logs/livetalking.log"
VENV_BIN="$PROJECT_DIR/.venv/bin/python"

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $message"
}

# 检查服务状态
status() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ LiveTalking 服务正在运行${NC}"
            echo -e "${BLUE}PID: $pid${NC}"
            ps -p "$pid" -o pid,pcpu,pmem,etime,command | tail -1
            return 0
        else
            echo -e "${YELLOW}⚠️  PID 文件存在但进程未运行，清理 PID 文件${NC}"
            rm -f "$PID_FILE"
            return 1
        fi
    else
        echo -e "${RED}❌ LiveTalking 服务未运行${NC}"
        return 1
    fi
}

# 启动服务
start() {
    print_message "$BLUE" "========================================="
    print_message "$BLUE" "🚀 启动 LiveTalking 服务"
    print_message "$BLUE" "========================================="

    # 检查是否已经运行
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            print_message "$YELLOW" "⚠️  服务已在运行中 (PID: $pid)"
            return 1
        else
            print_message "$YELLOW" "清理旧的 PID 文件"
            rm -f "$PID_FILE"
        fi
    fi

    # 检查 SRS 是否运行
    if ! docker ps | grep -q "srs"; then
        print_message "$YELLOW" "⚠️  SRS 未运行，正在启动..."
        cd "$PROJECT_DIR"
        docker compose up -d srs
        sleep 3
    fi

    cd "$PROJECT_DIR"

    # 加载 .env 文件中的环境变量
    if [ -f "$PROJECT_DIR/.env" ]; then
        print_message "$BLUE" "📄 加载 .env 配置文件..."
        set -a
        source "$PROJECT_DIR/.env"
        set +a
    fi

    # 设置环境变量
    export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/src:$(pwd)/src/core:$(pwd)/src/llm:$(pwd)/src/utils:$(pwd)/src/main"
    export OMP_NUM_THREADS=8
    export PYTHONHASHSEED=0
    export MKL_NUM_THREADS=8

    # 从 .env 获取 TTS 类型，默认为 doubao
    TTS_TYPE=${TTS_TYPE:-doubao}
    DOUBAO_VOICE_ID=${DOUBAO_VOICE_ID:-zh_female_tianxinxiaomei_emo_v2_mars_bigtts}

    print_message "$BLUE" "📝 配置参数:"
    print_message "$BLUE" "   - FPS: 25"
    print_message "$BLUE" "   - 分辨率: 384x384"
    print_message "$BLUE" "   - Batch Size: 16 (优化: 最大吞吐量)"
    print_message "$BLUE" "   - TTS: $TTS_TYPE"
    print_message "$BLUE" "   - Voice: $DOUBAO_VOICE_ID"
    print_message "$BLUE" "   - ASR: Lip"
    print_message "$BLUE" "   - Max Sessions: 5"
    print_message "$BLUE" "   - 日志文件: $LOG_FILE"

    # 后台启动服务
    cd "$PROJECT_DIR"
    nohup "$VENV_BIN" src/main/app.py \
        --transport rtcpush \
        --push_url "http://localhost:1985/rtc/v1/whip/?app=live&stream=livestream" \
        --model wav2lip \
        --fps 25 \
        -l 8 -m 6 -r 8 \
        --W 384 --H 384 \
        --batch_size 16 \
        --listenport 8010 \
        --avatar_id wav2lip256_avatar1 \
        --tts $TTS_TYPE \
        --REF_FILE $DOUBAO_VOICE_ID \
        --asr lip \
        --max_session 5 \
        >> "$LOG_FILE" 2>&1 &

    local pid=$!
    echo $pid > "$PID_FILE"

    # 等待启动
    sleep 3

    # 验证服务是否启动成功
    if ps -p "$pid" > /dev/null 2>&1; then
        print_message "$GREEN" "✅ 服务启动成功！"
        print_message "$GREEN" "   PID: $pid"
        print_message "$GREEN" "   日志: tail -f $LOG_FILE"
        print_message "$GREEN" "   前端: http://localhost:1420"
        print_message "$GREEN" "   SRS: http://localhost:8080/console/"
        status
    else
        print_message "$RED" "❌ 服务启动失败，请检查日志: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

# 停止服务
stop() {
    print_message "$YELLOW" "⏹️  停止 LiveTalking 服务..."

    if [ ! -f "$PID_FILE" ]; then
        print_message "$YELLOW" "⚠️  服务未运行"
        return 0
    fi

    local pid=$(cat "$PID_FILE")

    if ps -p "$pid" > /dev/null 2>&1; then
        kill "$pid"
        print_message "$YELLOW" "   发送 TERM 信号到 PID: $pid"

        # 等待进程结束（最多 10 秒）
        local count=0
        while ps -p "$pid" > /dev/null 2>&1 && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done

        # 如果进程还在运行，强制终止
        if ps -p "$pid" > /dev/null 2>&1; then
            print_message "$RED" "   ⚠️  强制终止进程..."
            kill -9 "$pid"
            sleep 1
        fi

        print_message "$GREEN" "✅ 服务已停止"
    else
        print_message "$YELLOW" "⚠️  进程未运行"
    fi

    rm -f "$PID_FILE"
}

# 重启服务
restart() {
    print_message "$BLUE" "🔄 重启 LiveTalking 服务"
    stop
    sleep 2
    start
}

# 查看日志
logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        print_message "$RED" "❌ 日志文件不存在: $LOG_FILE"
    fi
}

# 查看最近的错误
errors() {
    if [ -f "$LOG_FILE" ]; then
        grep -E "ERROR|Exception|error" "$LOG_FILE" | tail -20
    else
        print_message "$RED" "❌ 日志文件不存在: $LOG_FILE"
    fi
}

# 显示帮助信息
usage() {
    echo "LiveTalking 服务管理脚本"
    echo ""
    echo "用法: $0 {start|stop|restart|status|logs|errors}"
    echo ""
    echo "命令:"
    echo "  start    - 启动服务（后台运行）"
    echo "  stop     - 停止服务"
    echo "  restart  - 重启服务"
    echo "  status   - 查看服务状态"
    echo "  logs     - 查看实时日志"
    echo "  errors   - 查看最近的错误"
    echo ""
    echo "示例:"
    echo "  $0 start      # 启动服务"
    echo "  $0 status     # 查看状态"
    echo "  $0 logs       # 查看日志"
}

# 主程序
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    errors)
        errors
        ;;
    *)
        usage
        exit 1
        ;;
esac

exit $?
