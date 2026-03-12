# LiveTalking Frontend Dockerfile
# 用于构建和部署 Desktop App 前端（支持 HTTPS）

# 构建阶段
FROM node:20-alpine AS builder

WORKDIR /app

# 设置 npm 镜像源（加速构建）
RUN npm config set registry https://registry.npmmirror.com

# 复制 package 文件
COPY package*.json ./

# 安装依赖
RUN npm install

# 复制源代码（排除 node_modules 和其他不需要的文件）
COPY . .

# 构建前端
RUN npm run build

# 生产阶段 - 使用 Nginx 提供 HTTPS
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /app/dist

# 复制 SSL 证书（将在构建时从主机复制）
COPY ssl/cert.pem /etc/nginx/ssl/cert.pem
COPY ssl/key.pem /etc/nginx/ssl/key.pem

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/nginx.conf

# 暴露端口
EXPOSE 1420 8443

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-check-certificate --no-verbose --tries=1 --spider https://localhost:1420/ || exit 1
