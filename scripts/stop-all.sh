#!/bin/bash
# LiveTalking 一键停止脚本
# ==========================================

PROJECT_DIR="/Users/lukeding/Desktop/playground/2025/LiveTalking"

echo "⏹️  停止 LiveTalking 服务"
echo "================================"
echo ""

# 1. 停止后端服务
echo "🐍 停止后端服务..."
cd "$PROJECT_DIR"
./livetalking-daemon.sh stop
echo ""

# 2. 询问是否停止 SRS
echo "📡 是否停止 SRS 服务？"
echo "   注意：如果其他服务依赖 SRS，请选择 n"
read -p "停止 SRS? (y/n): " stop_srs

if [ "$stop_srs" = "y" ] || [ "$stop_srs" = "Y" ]; then
    echo "   🔄 停止 SRS..."
    docker compose down srs
    echo "   ✅ SRS 已停止"
else
    echo "   ⏭️  保留 SRS 运行"
fi
echo ""

echo "✅ 服务已停止"
echo ""
