# LiveTalking 前端本地打包部署指南

## 📋 方案说明

由于服务器网络问题，使用**本地打包 + 服务器部署**的方案，避免在Docker构建时下载大量依赖。

## 🚀 快速开始

### 步骤1：本地打包（在Mac上执行）

```bash
cd /Users/lukeding/Desktop/playground/2025/LiveTalking

# 运行打包脚本
./build-frontend-local.sh
```

**输出：**
- ✅ 构建文件：`docker/frontend-dist/dist/`
- ✅ 构建信息：`docker/frontend-dist/build-info.txt`
- 📦 文件大小：约 5-10MB

### 步骤2：上传到服务器

```bash
# 在Mac上执行
scp -r docker/frontend-dist root@your-server-ip:/opt/lt/docker/
```

**或使用rsync（更快）：**
```bash
rsync -avz --progress docker/frontend-dist/ root@your-server-ip:/opt/lt/docker/frontend-dist/
```

### 步骤3：服务器部署

```bash
# SSH登录服务器
ssh root@your-server-ip

# 进入目录
cd /opt/lt/docker

# 运行部署脚本
chmod +x deploy-frontend-local.sh
./deploy-frontend-local.sh
```

## 📁 文件说明

### 本地文件
- `build-frontend-local.sh` - 本地打包脚本
- `docker/Dockerfile.frontend.local` - 使用本地打包文件的Dockerfile
- `docker/nginx.conf` - Nginx配置文件

### 服务器文件
- `docker/deploy-frontend-local.sh` - 服务器部署脚本
- `docker/frontend-dist/` - 上传的打包文件

## 🔧 工作原理

```
本地Mac                          服务器
────────                         ──────
1. 运行build-frontend-local.sh
   └─ yarn install (本地网络快)
   └─ yarn build
   └─ 生成 docker/frontend-dist/
                              ↓
2. 上传frontend-dist/
                              ↓
3. 运行deploy-frontend-local.sh
   └─ docker-compose build
      └─ 使用Dockerfile.frontend.local
      └─ 直接复制dist文件（无需下载依赖）
   └─ docker-compose up -d
```

## ⚡ 优势对比

| 方案 | 依赖下载 | 构建时间 | 网络要求 |
|------|---------|---------|---------|
| **Docker直接构建** | 服务器下载 | ~15分钟 | 需要稳定网络 |
| **本地打包部署** | 本地下载 | ~2分钟 | 只需上传小文件 |

## 🛠️ 故障排查

### 问题1：本地构建失败

```bash
# 清理并重新安装
cd frontend/desktop_app
rm -rf node_modules dist
yarn install
yarn build
```

### 问题2：上传失败

```bash
# 检查服务器连接
ping your-server-ip

# 使用更详细的scp命令
scp -v -r docker/frontend-dist root@your-server-ip:/opt/lt/docker/
```

### 问题3：服务器部署失败

```bash
# 检查文件是否上传成功
ls -la /opt/lt/docker/frontend-dist/

# 检查Docker是否运行
docker ps

# 查看构建日志
docker-compose logs frontend
```

## 📝 验证部署

```bash
# 在服务器上检查
docker-compose ps
curl http://localhost/

# 应该看到前端页面
```

## 🔐 安全建议

1. **使用SSH密钥**而不是密码
2. **限制上传文件大小**（dist目录）
3. **定期清理**旧的frontend-dist目录

## 🎯 下次更新

当需要更新前端时：

```bash
# 本地
./build-frontend-local.sh
scp -r docker/frontend-dist root@server:/opt/lt/docker/

# 服务器
cd /opt/lt/docker
./deploy-frontend-local.sh
```

---

**注意**: 后端服务仍然使用Docker直接构建，因为后端依赖已经在requirements.txt中锁定，且pip通常比npm/yarn更稳定。
