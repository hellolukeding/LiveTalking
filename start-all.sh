#!/bin/bash
# LiveTalking 一键启动脚本
# ==========================================

PROJECT_DIR="/Users/lukeding/Desktop/playground/2025/LiveTalking"
DESKTOP_APP_DIR="$PROJECT_DIR/frontend/desktop_app"

echo "🚀 LiveTalking 一键启动"
echo "================================"
echo ""

# 1. 启动 SRS (如果未运行)
echo "📡 检查 SRS 服务..."
if docker ps | grep -q "srs"; then
    echo "   ✅ SRS 已在运行"
else
    echo "   🔄 启动 SRS..."
    cd "$PROJECT_DIR"
    docker compose up -d srs
    sleep 3
    echo "   ✅ SRS 启动成功"
fi
echo ""

# 2. 启动后端服务
echo "🐍 启动后端服务..."
cd "$PROJECT_DIR"
./livetalking-daemon.sh start
if [ $? -eq 0 ]; then
    echo "   ✅ 后端服务已启动"
else
    echo "   ❌ 后端服务启动失败"
    exit 1
fi
echo ""

# 3. 等待后端就绪
echo "⏳ 等待后端服务就绪..."
sleep 5
echo "   ✅ 后端服务就绪"
echo ""

# 4. 启动前端（可选）
echo "💻 前端启动方式："
echo "   方式1（开发模式）:"
echo "      cd $DESKTOP_APP_DIR"
echo "      npm run dev"
echo ""
echo "   方式2（构建后运行）:"
echo "      cd $DESKTOP_APP_DIR"
echo "      npm run build"
echo "      npm run tauri dev"
echo ""

# 5. 显示访问地址
echo "✅ 所有服务已启动！"
echo ""
echo "📱 访问地址:"
echo "   前端开发: http://localhost:1420"
echo "   SRS 控制台: http://localhost:8080/console/"
echo "   FLV 播放: http://localhost:8080/live/livestream.flv"
echo ""
echo "🔧 管理命令:"
echo "   查看状态: ./livetalking-daemon.sh status"
echo "   查看日志: ./livetalking-daemon.sh logs"
echo "   停止服务: ./livetalking-daemon.sh stop"
echo "   重启服务: ./livetalking-daemon.sh restart"
echo ""
