# LiveTalking Frontend Dockerfile
# 用于构建和部署 Desktop App 前端

# 构建阶段
FROM node:20-alpine AS builder

WORKDIR /app

# 安装依赖
COPY package*.json ./
RUN npm ci

# 复制源代码并构建
COPY . .
RUN npm run build

# 生产阶段
FROM node:20-alpine

WORKDIR /app

# 安装 serve 用于静态文件服务
RUN npm install -g serve

# 从构建阶段复制构建产物
COPY --from=builder /app/dist /app/dist

# 暴露端口
EXPOSE 1420

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:1420/ || exit 1

# 启动服务
CMD ["serve", "-s", "dist", "-l", "1420"]
