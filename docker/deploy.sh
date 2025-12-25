#!/bin/bash
set -e

echo "=== LiveTalking Docker 部署脚本 ==="

if [ "$EUID" -ne 0 ]; then
    echo "请使用root权限运行: sudo $0"
    exit 1
fi

if [ $# -eq 0 ]; then
    echo "用法: $0 [install|setup|start|stop|restart|logs|status|help]"
    exit 1
fi

command=$1

case $command in
    install)
        echo "安装Docker和NVIDIA容器工具包..."
        apt-get update
        apt-get install -y docker.io docker-compose nvidia-container-toolkit
        systemctl enable docker
        systemctl start docker
        nvidia-ctk runtime configure --runtime=docker
        systemctl restart docker
        echo "安装完成"
        ;;
        
    setup)
        echo "准备环境配置..."
        mkdir -p models data logs ssl
        
        if [ ! -f ../.env ]; then
            cat > ../.env << 'ENVEOF'
LISTEN_PORT=8011
MAX_SESSION=1
FPS=30
MODEL=wav2lip
AVATAR_ID=wav2lip256_avatar1
TTS_TYPE=doubao
DOUBAO_APPID=your_appid
DOUBAO_ACCESS_TOKEN=your_token
DOUBAO_VOICE_ID=zh_female_xiaohe_uranus_bigtts
DOUBAO_RESOURCE_ID=your_resource_id
ASR_TYPE=lip
CUDA_VISIBLE_DEVICES=0
ENVEOF
            echo "已创建 ../.env，请编辑配置"
        fi
        
        if [ ! -f ssl/cert.pem ]; then
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout ssl/key.pem -out ssl/cert.pem \
                -subj "/C=CN/ST=Beijing/L=Beijing/O=LiveTalking/CN=localhost"
            echo "已生成自签名SSL证书"
        fi
        # 尝试构建前端（如果存在 Node.js 环境）
        FRONTEND_DIR="../frontend/desktop_app"
        if command -v node >/dev/null 2>&1 && [ -d "$FRONTEND_DIR" ]; then
            echo "检测到 Node.js，正在构建前端..."
            pushd "$FRONTEND_DIR" >/dev/null
            if [ -f package-lock.json ]; then
                npm ci --no-audit --no-fund
            else
                npm install --no-audit --no-fund
            fi
            npm run build --if-present
            popd >/dev/null
            echo "前端构建完成，输出目录: $FRONTEND_DIR/dist"
        else
            echo "跳过前端构建：未检测到 Node.js 或前端目录不存在"
            echo "你可以手动构建前端：cd frontend/desktop_app && npm ci && npm run build"
        fi
        echo "环境准备完成"
        ;;
        
    start)
        echo "构建并启动服务..."
        docker compose build
        docker compose up -d
        sleep 5
        if docker compose ps | grep -q "Up"; then
            echo "✅ 服务已启动"
            echo "访问: http://localhost:8011"
        else
            echo "❌ 启动失败"
            docker compose logs
            exit 1
        fi
        ;;
        
    stop)
        echo "停止服务..."
        docker compose down
        ;;
        
    restart)
        echo "重启服务..."
        docker compose restart
        ;;
        
    logs)
        docker compose logs -f
        ;;
        
    status)
        docker compose ps
        echo ""
        docker stats --no-stream
        ;;
        
    help|--help|-h)
        echo "LiveTalking Docker 部署脚本"
        echo ""
        echo "命令:"
        echo "  install  - 安装Docker和NVIDIA工具包"
        echo "  setup    - 准备环境和配置"
        echo "  start    - 启动服务"
        echo "  stop     - 停止服务"
        echo "  restart  - 重启服务"
        echo "  logs     - 查看日志"
        echo "  status   - 查看状态"
        echo ""
        echo "示例:"
        echo "  $0 install"
        echo "  $0 setup"
        echo "  $0 start"
        ;;
        
    *)
        echo "未知命令: $command"
        echo "使用 $0 help 查看帮助"
        exit 1
        ;;
esac
