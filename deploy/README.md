# LiveTalking 部署文档

本目录包含 LiveTalking 项目的本地部署脚本和配置文件。

## 目录结构

```
deploy/
├── livetalking.conf.template    # 配置文件模板
├── livetalking-backend.service  # systemd 服务文件
├── backend.sh                   # 后端控制脚本
├── control.sh                   # 交互式控制面板
├── deploy.sh                    # 一键部署脚本
├── frontend/                    # 前端 Docker 部署
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── deploy.sh
└── README.md                    # 本文档
```

## 快速开始

### 后端部署（本机直接部署）

```bash
# 1. 进入项目目录
cd /opt/2026/LiveTalking

# 2. 执行部署脚本
chmod +x deploy/deploy.sh
sudo deploy/deploy.sh

# 3. 启动服务
deploy/backend.sh start
```

### 前端部署（Docker）

```bash
# 1. 部署前端
cd deploy/frontend
chmod +x deploy.sh
./deploy.sh

# 2. 访问前端
# http://localhost:1420
```

## 配置说明

### 后端配置文件

配置文件位于 `deploy/livetalking.conf`，首次部署时会从模板自动创建。

**主要配置项：**

```bash
# 基础配置
PROJECT_ROOT="/opt/2026/LiveTalking"    # 项目根目录
VENV_PATH="$PROJECT_ROOT/.venv"         # Python 虚拟环境
LISTEN_PORT=8010                         # 监听端口

# 模型配置
MODEL_TYPE="wav2lip"                     # 模型类型
AVATAR_ID="wav2lip256_avatar1"          # 形象 ID

# TTS 配置
TTS_TYPE="doubao"                        # TTS 服务类型
DOUBAO_VOICE_ID="zh_female_xiaohe_uranus_bigtts"  # 豆包语音 ID

# WebRTC 配置
VIDEO_BITRATE=5000                       # 视频码率 (kbps)
VIDEO_CODEC="auto"                       # 视频编解码器
```

**配置编辑方式：**

```bash
# 方式1: 使用控制面板
./deploy/control.sh
# 选择 7. 配置管理 -> 1. 编辑配置文件

# 方式2: 直接编辑
nano deploy/livetalking.conf
```

## 服务管理

### 后端服务管理

**命令行方式：**

```bash
# 启动服务
./deploy/backend.sh start

# 停止服务
./deploy/backend.sh stop

# 重启服务
./deploy/backend.sh restart

# 查看状态
./deploy/backend.sh status

# 查看日志
./deploy/backend.sh logs

# 实时日志
./deploy/backend.sh follow
```

**交互式控制面板：**

```bash
./deploy/control.sh
```

**systemd 方式：**

```bash
# 安装服务后
sudo systemctl start livetalking-backend
sudo systemctl stop livetalking-backend
sudo systemctl restart livetalking-backend
sudo systemctl status livetalking-backend

# 开机自启
sudo systemctl enable livetalking-backend
```

### 前端服务管理

```bash
cd deploy/frontend

# 启动/停止/重启
./deploy.sh start
./deploy.sh stop
./deploy.sh restart

# 查看状态和日志
./deploy.sh status
./deploy.sh logs

# 重新构建镜像
./deploy.sh build
```

## 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 8010 | 后端 | LiveTalking API 和 WebRTC 服务 |
| 1420 | 前端 | Web 界面 |

## 访问地址

### 后端 API

- **WebRTC API**: http://localhost:8010/webrtcapi.html
- **Dashboard**: http://localhost:8010/dashboard.html
- **Avatar API**: http://localhost:8010/avatars

### 前端界面

- **Desktop App**: http://localhost:1420

## 日志位置

| 日志类型 | 路径 |
|----------|------|
| 后端主日志 | `/opt/2026/LiveTalking/logs/livetalking.log` |
| 后端错误日志 | `/opt/2026/LiveTalking/logs/error.log` |
| systemd 日志 | `/opt/2026/LiveTalking/logs/systemd.log` |

查看日志：
```bash
# 实时查看
tail -f /opt/2026/LiveTalking/logs/livetalking.log

# 或使用控制脚本
./deploy/backend.sh follow
```

## 故障排查

### 后端无法启动

1. **检查配置文件**
   ```bash
   ./deploy/backend.sh status
   ```

2. **查看错误日志**
   ```bash
   tail -100 /opt/2026/LiveTalking/logs/error.log
   ```

3. **检查端口占用**
   ```bash
   netstat -tlnp | grep 8010
   ```

4. **检查虚拟环境**
   ```bash
   source .venv/bin/activate
   python --version
   pip list
   ```

### 前端无法连接后端

1. **检查后端是否运行**
   ```bash
   curl http://localhost:8010/avatars
   ```

2. **检查 Vite 代理配置**
   - 文件：`frontend/desktop_app/vite.config.ts`
   - 确认 `/avatars` 代理到 `http://localhost:8010`

3. **检查网络连接**
   ```bash
   # 测试后端 API
   curl http://localhost:8010/avatars

   # 测试代理（从前端容器内）
   docker exec livetalking-frontend wget -O- http://localhost:8010/avatars
   ```

### 模型加载失败

1. **检查模型文件**
   ```bash
   ls -la models/
   # 应包含 wav2lip256.pth 等模型文件
   ```

2. **检查形象数据**
   ```bash
   ls -la data/avatars/
   # 应包含形象目录
   ```

3. **检查 CUDA/GPU**
   ```bash
   python -c "import torch; print(torch.cuda.is_available())"
   ```

## 升级和维护

### 更新依赖

```bash
# 更新 Python 依赖
./deploy/deploy.sh update

# 重新构建前端
cd deploy/frontend
./deploy.sh build
```

### 备份和恢复

**备份：**
```bash
# 备份配置和数据
tar czf livetalking-backup-$(date +%Y%m%d).tar.gz \
    deploy/livetalking.conf \
    data/avatars/ \
    models/
```

**恢复：**
```bash
tar xzf livetalking-backup-YYYYMMDD.tar.gz
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

## 生产环境建议

1. **使用反向代理**
   - 使用 Nginx 或 Caddy 作为反向代理
   - 配置 HTTPS/SSL 证书

2. **启用防火墙**
   ```bash
   # 仅开放必要端口
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw allow 1420/tcp
   ufw enable
   ```

3. **配置日志轮转**
   ```bash
   # 创建 logrotate 配置
   cat > /etc/logrotate.d/livetalking << EOF
   /opt/2026/LiveTalking/logs/*.log {
       daily
       rotate 7
       compress
       delaycompress
       missingok
       notifempty
   }
   EOF
   ```

4. **监控和告警**
   - 设置 systemd 服务监控
   - 配置日志分析和告警
   - 监控资源使用情况

## 技术支持

- **GitHub Issues**: https://github.com/hellolukeding/LiveTalking/issues
- **文档**: 项目根目录 README.md
