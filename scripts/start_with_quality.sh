#!/bin/bash
# ============================================================================
# LiveTalking 服务启动脚本 - 支持视频质量配置
# ============================================================================

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 默认配置
MODEL="${MODEL:-wav2lip}"
TTS="${TTS:-doubao}"
VIDEO_BITRATE="${VIDEO_BITRATE:-5000}"
VIDEO_CODEC="${VIDEO_CODEC:-auto}"
W="${W:-450}"
H="${H:-450}"

# 显示帮助
show_help() {
    echo ""
    echo "LiveTalking 服务启动脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -b, --bitrate <kbps>     视频码率 (默认: 5000)"
    echo "  -c, --codec <codec>      视频编码器 (默认: auto)"
    echo "  -W, --width <px>         输出宽度 (默认: 450)"
    echo "  -H, --height <px>        输出高度 (默认: 450)"
    echo "  -m, --model <model>      模型类型 (默认: wav2lip)"
    echo "  -t, --tts <service>      TTS服务 (默认: doubao)"
    echo "  -q, --quality <level>     快速设置质量预设"
    echo ""
    echo "质量预设:"
    echo "  low    -> 2000 kbps, H264"
    echo "  medium -> 3000 kbps, auto"
    echo "  high   -> 5000 kbps, auto (默认)"
    echo "  ultra  -> 8000 kbps, VP9"
    echo ""
    echo "示例:"
    echo "  $0                    # 高质量启动"
    echo "  $0 -q ultra          # 超高质量"
    echo "  $0 -b 6000           # 自定义码率"
    echo "  $0 -W 720 -H 720     # 高分辨率"
    echo ""
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--bitrate)
            VIDEO_BITRATE="$2"
            shift 2
            ;;
        -c|--codec)
            VIDEO_CODEC="$2"
            shift 2
            ;;
        -W|--width)
            W="$2"
            shift 2
            ;;
        -H|--height)
            H="$2"
            shift 2
            ;;
        -q|--quality)
            QUALITY="$2"
            case "$QUALITY" in
                low)
                    VIDEO_BITRATE=2000
                    VIDEO_CODEC="H264"
                    ;;
                medium)
                    VIDEO_BITRATE=3000
                    VIDEO_CODEC="auto"
                    ;;
                high)
                    VIDEO_BITRATE=5000
                    VIDEO_CODEC="auto"
                    ;;
                ultra)
                    VIDEO_BITRATE=8000
                    VIDEO_CODEC="VP9"
                    ;;
                *)
                    echo "错误: 未知质量预设 '$QUALITY'"
                    exit 1
                    ;;
            esac
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "错误: 未知选项 '$1'"
            show_help
            exit 1
            ;;
    esac
done

# 设置 PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/src:$PROJECT_ROOT/src/main:$PROJECT_ROOT/src/core:$PROJECT_ROOT/src/utils:$PROJECT_ROOT/src/llm"

# 显示配置
echo "=================================================="
echo "  LiveTalking 服务启动"
echo "=================================================="
echo "  模型:         $MODEL"
echo "  TTS:          $TTS"
echo "  视频分辨率:   ${W}x${H}"
echo "  视频码率:     $VIDEO_BITRATE kbps"
echo "  视频编码器:   $VIDEO_CODEC"
echo "=================================================="
echo ""

# 停止旧服务
if pgrep -f "python.*app.py" > /dev/null; then
    echo "停止现有服务..."
    pkill -f "python.*app.py"
    sleep 2
fi

# 启动服务
echo "启动服务..."
nohup .venv/bin/python src/main/app.py \
    --model "$MODEL" \
    --tts "$TTS" \
    --video_bitrate "$VIDEO_BITRATE" \
    --video_codec "$VIDEO_CODEC" \
    --W "$W" \
    --H "$H" \
    > /tmp/livetalking.log 2>&1 &

PID=$!
sleep 3

# 检查服务状态
if ps -p $PID > /dev/null; then
    echo "服务已启动 (PID: $PID)"
    echo ""
    echo "查看日志: tail -f /tmp/livetalking.log"
    echo "停止服务: pkill -f 'python.*app.py'"
else
    echo "服务启动失败"
    echo "查看日志: cat /tmp/livetalking.log"
    exit 1
fi
