# 快速部署指南 - LiveTalking

## 🎯 前端打包（配置后端API地址）

### 本地开发环境
```bash
# 使用默认API地址 (http://localhost:8010)
./build-frontend-local.sh
```

### 生产环境（配置服务器IP）
```bash
# 方法1：直接传入API地址
./build-frontend-local.sh http://192.168.1.100:8010

# 方法2：使用域名
./build-frontend-local.sh https://api.yourdomain.com

# 方法3：本地测试其他IP
./build-frontend-local.sh http://10.0.0.5:8010
```

## 📦 完整部署流程

### 场景1：部署到服务器 (IP: 192.168.1.100)

```bash
# 1. 本地打包（指定服务器IP）
./build-frontend-local.sh http://192.168.1.100:8010

# 2. 上传到服务器
scp -r docker/frontend-dist root@192.168.1.100:/opt/lt/docker/

# 3. 服务器部署
ssh root@192.168.1.100
cd /opt/lt/docker
./deploy-frontend-local.sh
```

### 场景2：本地开发测试

```bash
# 使用默认配置即可
./build-frontend-local.sh

# 前端会连接 http://localhost:8010
```

## 🔧 常见配置示例

| 环境 | API地址 | 命令 |
|------|---------|------|
| **本地开发** | http://localhost:8010 | `./build-frontend-local.sh` |
| **局域网服务器** | http://192.168.1.100:8010 | `./build-frontend-local.sh http://192.168.1.100:8010` |
| **公网服务器** | https://api.example.com | `./build-frontend-local.sh https://api.example.com` |
| **Docker内网** | http://backend:8010 | `./build-frontend-local.sh http://backend:8010` |

## ⚡ 快速修改并重新打包

```bash
# 修改API地址后重新打包
./build-frontend-local.sh http://新地址:8010

# 确认配置
cat docker/frontend-dist/build-info.txt

# 重新上传
scp -r docker/frontend-dist root@server:/opt/lt/docker/
```

## 📝 查看当前配置

```bash
# 查看构建信息（包含API地址）
cat docker/frontend-dist/build-info.txt

# 输出示例：
# 构建时间: 2026-01-30 12:00:00
# 构建主机: MacBook-Pro.local
# 构建用户: yourname
# Git Commit: abc1234
# 后端API: http://192.168.1.100:8010  ← 这是配置的API地址
```

## 🚨 注意事项

1. **API地址必须可访问**
   - 确保前端能访问到后端API地址
   - 检查防火墙和网络配置

2. **HTTPS vs HTTP**
   - 本地开发用HTTP
   - 生产环境建议用HTTPS

3. **端口配置**
   - 默认后端端口：8010
   - 如果修改了端口，需要同步更新

4. **跨域问题**
   - 如果前后端分离部署，需要配置CORS

## 💡 最佳实践

1. **开发环境**：使用默认配置 `http://localhost:8010`
2. **测试环境**：使用服务器IP `http://test-server:8010`
3. **生产环境**：使用域名 `https://api.yourdomain.com`

---

**就这么简单！一个命令搞定配置和打包！**
