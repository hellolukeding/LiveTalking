# LiveTalking 本地部署快速指南

本指南帮助您在本地机器上快速部署 LiveTalking。

## 系统要求

- **操作系统**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- **Python**: 3.8 或更高版本
- **内存**: 建议 8GB+ (GPU 推理需要更多内存)
- **磁盘**: 至少 20GB 可用空间
- **Docker**: 前端部署需要 Docker 和 Docker Compose

## 一键部署后端

```bash
# 进入项目目录
cd /opt/2026/LiveTalking

# 执行部署脚本
sudo deploy/deploy.sh
```

部署脚本会自动完成以下操作：
1. 检查系统环境
2. 安装系统依赖
3. 创建 Python 虚拟环境
4. 安装 Python 依赖包
5. 生成配置文件
6. 设置文件权限
7. 安装 systemd 服务（可选）

## 手动部署后端

如果自动部署失败，可以按以下步骤手动部署：

### 1. 安装系统依赖

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg curl wget git

# CentOS/RHEL
sudo yum install -y python3 python3-venv python3-pip ffmpeg curl wget git
```

### 2. 创建虚拟环境

```bash
cd /opt/2026/LiveTalking
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

### 3. 安装 Python 依赖

```bash
# 使用完整依赖列表
pip install -r requirements_full.txt

# 或使用基础依赖列表
pip install -r requirements.txt
```

### 4. 配置服务

```bash
# 从模板创建配置文件
cp deploy/livetalking.conf.template deploy/livetalking.conf

# 编辑配置（可选，使用默认配置也可直接启动）
nano deploy/livetalking.conf
```

### 5. 启动服务

```bash
# 使用控制脚本启动
./deploy/backend.sh start

# 或直接启动
PYTHONPATH=/opt/2026/LiveTalking:/opt/2026/LiveTalking/src:/opt/2026/LiveTalking/src/main:/opt/2026/LiveTalking/src/core:/opt/2026/LiveTalking/src/utils:/opt/2026/LiveTalking/src/services \
.venv/bin/python src/main/app.py \
  --model wav2lip \
  --tts doubao \
  --avatar_id wav2lip256_avatar1 \
  --listenport 8010 \
  --video_bitrate 5000
```

## 部署前端（Docker）

### 方式一：使用部署脚本

```bash
cd deploy/frontend
./deploy.sh
```

### 方式二：手动部署

```bash
cd deploy/frontend

# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 验证部署

### 检查后端服务

```bash
# 查看服务状态
./deploy/backend.sh status

# 测试 API
curl http://localhost:8010/avatars

# 应返回类似内容：
# {"code": 0, "data": [...]}
```

### 检查前端服务

```bash
# 查看容器状态
cd deploy/frontend
docker-compose ps

# 测试访问
curl http://localhost:1420
```

### 完整测试

1. **访问前端界面**
   - 打开浏览器访问: http://localhost:1420

2. **测试 WebRTC 连接**
   - 点击"开始对话"按钮
   - 检查是否能正常连接和显示视频

3. **测试语音交互**
   - 允许麦克风权限
   - 说话测试 TTS 和 ASR 功能

## 常用命令

### 后端服务控制

```bash
# 查看服务状态
./deploy/backend.sh status

# 启动服务
./deploy/backend.sh start

# 停止服务
./deploy/backend.sh stop

# 重启服务
./deploy/backend.sh restart

# 查看日志
./deploy/backend.sh logs

# 实时日志
./deploy/backend.sh follow
```

### 前端服务控制

```bash
cd deploy/frontend

# 查看状态
./deploy.sh status

# 重启服务
./deploy.sh restart

# 查看日志
./deploy.sh logs
```

### 使用 systemd 管理（如果已安装）

```bash
# 启动服务
sudo systemctl start livetalking-backend

# 停止服务
sudo systemctl stop livetalking-backend

# 重启服务
sudo systemctl restart livetalking-backend

# 查看状态
sudo systemctl status livetalking-backend

# 开机自启
sudo systemctl enable livetalking-backend
```

## 配置说明

### 修改端口

编辑 `deploy/livetalking.conf`:

```bash
# 后端端口（默认 8010）
LISTEN_PORT=8010
```

编辑 `deploy/frontend/docker-compose.yml`:

```yaml
services:
  livetalking-frontend:
    ports:
      - "1420:1420"  # 前端端口
```

### 配置 TTS

编辑 `deploy/livetalking.conf`:

```bash
# 豆包 TTS
TTS_TYPE="doubao"
DOUBAO_VOICE_ID="zh_female_xiaohe_uranus_bigtts"
DOUBAO_API_KEY="your_api_key"
DOUBAO_APP_ID="your_app_id"

# Edge TTS（免费，无需配置）
TTS_TYPE="edge"
EDGE_TTS_VOICE="zh-CN-XiaoxiaoNeural"

# 腾讯 TTS
TTS_TYPE="tencent"
TENCENT_VOICE_TYPE="1001"
TENCENT_SECRET_ID="your_secret_id"
TENCENT_SECRET_KEY="your_secret_key"
```

### 配置视频质量

```bash
# 视频码率（建议 2000-8000 kbps）
VIDEO_BITRATE=5000

# 视频编解码器（auto/VP9/H264/VP8）
VIDEO_CODEC="auto"
```

## 故障排查

### 问题 1: 后端无法启动

```bash
# 查看错误日志
tail -100 /opt/2026/LiveTalking/logs/error.log

# 检查端口占用
netstat -tlnp | grep 8010

# 手动启动测试
cd /opt/2026/LiveTalking
source .venv/bin/activate
python src/main/app.py --model wav2lip --tts doubao
```

### 问题 2: 前端无法连接后端

```bash
# 确认后端运行
curl http://localhost:8010/avatars

# 检查网络
ping localhost
telnet localhost 8010

# 检查 Docker 网络
docker network ls
docker network inspect livetalking-network
```

### 问题 3: 模型加载失败

```bash
# 检查模型文件
ls -la models/

# 检查 CUDA（如果使用 GPU）
python -c "import torch; print(torch.cuda.is_available())"

# 查看完整日志
./deploy/backend.sh logs 100
```

## 卸载

### 后端卸载

```bash
# 停止服务
./deploy/backend.sh stop

# 禁用 systemd 服务
sudo systemctl disable livetalking-backend
sudo rm /etc/systemd/system/livetalking-backend.service
sudo systemctl daemon-reload

# 删除虚拟环境（可选）
rm -rf /opt/2026/LiveTalking/.venv
```

### 前端卸载

```bash
cd deploy/frontend
./deploy.sh clean
```

## 下一步

- 阅读完整文档: `deploy/README.md`
- 配置 Nginx 反向代理（生产环境推荐）
- 设置 SSL/HTTPS 证书
- 配置日志轮转和监控

## 技术支持

如遇问题，请访问:
- GitHub Issues: https://github.com/hellolukeding/LiveTalking/issues
- 项目文档: 项目根目录 README.md
