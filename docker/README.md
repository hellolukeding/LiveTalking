# LiveTalking Docker 部署指南

本文档介绍如何使用 Docker 一键部署 LiveTalking 项目。

## 系统要求

### 基础要求
- Docker >= 20.10
- Docker Compose >= 2.0
- 至少 8GB RAM
- 至少 50GB 磁盘空间

### GPU 要求 (推荐)
- NVIDIA GPU >= RTX 3060
- CUDA >= 11.8
- NVIDIA Docker Runtime

### CPU 模式 (性能较低)
如果没有 GPU，可以在 CPU 模式下运行，但性能会显著降低。

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/lipku/LiveTalking.git
cd LiveTalking
```

### 2. 配置环境变量

```bash
cp docker/.env.example .env
# 编辑 .env 文件，配置您的 API 密钥
```

### 3. 一键部署

```bash
cd docker
./deploy.sh
```

部署脚本会自动完成以下操作：
- 检查系统依赖
- 创建必要的目录
- 构建 Docker 镜像
- 启动所有服务
- 显示访问地址

## 服务架构

部署后，系统将启动以下服务：

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| SRS | livetalking-srs | 1935, 1985, 8080, 8000 | 流媒体服务器 |
| Backend | livetalking-backend | 8010 | Python 后端服务 |
| Frontend | livetalking-frontend | 80 | React 前端应用 |
| Nginx | livetalking-nginx | 443 | 反向代理 (可选) |

## 访问地址

- **前端应用**: http://localhost
- **后端 API**: http://localhost:8010
- **SRS 控制台**: http://localhost:8080/console/
- **FLV 播放**: http://localhost:8080/live/livestream.flv

## 管理命令

### 查看服务状态

```bash
docker compose -f docker/docker-compose.yml ps
```

### 查看日志

```bash
# 查看所有服务日志
docker compose -f docker/docker-compose.yml logs -f

# 查看特定服务日志
docker compose -f docker/docker-compose.yml logs -f backend
docker compose -f docker/docker-compose.yml logs -f srs
```

### 停止服务

```bash
docker compose -f docker/docker-compose.yml down
```

### 重启服务

```bash
docker compose -f docker/docker-compose.yml restart
```

### 重新构建镜像

```bash
docker compose -f docker/docker-compose.yml build --no-cache
```

## 高级配置

### 仅构建镜像

```bash
cd docker
./deploy.sh --build-only
```

### 仅启动服务

```bash
cd docker
./deploy.sh --start-only
```

### 清理旧容器和镜像

```bash
cd docker
./deploy.sh --cleanup
```

### 启用 Nginx 反向代理

```bash
docker compose -f docker/docker-compose.yml --profile with-nginx up -d
```

### GPU 配置

确保已安装 NVIDIA Docker Runtime:

```bash
# 安装 NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

### 自定义端口

编辑 `docker/docker-compose.yml` 文件，修改端口映射：

```yaml
services:
  backend:
    ports:
      - "8011:8010"  # 将 8010 端口映射到主机的 8011
```

## 故障排查

### 1. 服务启动失败

查看日志：
```bash
docker compose -f docker/docker-compose.yml logs -f
```

### 2. GPU 不可用

检查 NVIDIA Docker：
```bash
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### 3. 端口冲突

修改 `docker/docker-compose.yml` 中的端口映射。

### 4. 内存不足

减少 `batch_size` 或 `max_session` 配置。

## 性能优化

### GPU 模式

确保 GPU 正确配置，可以获得最佳性能：
- FPS: 25-30
- 分辨率: 384x384 或 450x450
- Batch Size: 6-8
- Max Sessions: 3-5

### CPU 模式

如果使用 CPU，建议降低配置：
- FPS: 15-20
- 分辨率: 256x256
- Batch Size: 2-4
- Max Sessions: 1-2

## 生产环境部署

### 1. 使用 HTTPS

配置 SSL 证书：
```bash
mkdir -p docker/ssl
cp your-cert.pem docker/ssl/cert.pem
cp your-key.pem docker/ssl/key.pem
```

然后启用 Nginx：
```bash
docker compose -f docker/docker-compose.yml --profile with-nginx up -d
```

### 2. 配置防火墙

```bash
# 开放必要端口
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8010/tcp
```

### 3. 设置日志轮转

编辑 `/etc/logrotate.d/docker-livetalking`:
```
/path/to/docker/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 0644 root root
}
```

### 4. 监控和告警

建议使用以下工具：
- Prometheus + Grafana
- Docker Healthcheck
- 外部监控服务 (如 Datadog, New Relic)

## 更新部署

```bash
cd docker
git pull
./deploy.sh --cleanup
./deploy.sh
```

## 卸载

```bash
cd docker
docker compose down -v --remove-orphans
docker system prune -a
```

## 技术支持

- GitHub Issues: https://github.com/lipku/LiveTalking/issues
- 文档: https://github.com/lipku/LiveTalking/blob/main/README.md

## 许可证

Apache License 2.0
