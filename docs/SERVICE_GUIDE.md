# LiveTalking 服务端启动指南

## 📋 目录
- [快速启动](#快速启动)
- [详细启动步骤](#详细启动步骤)
- [服务管理命令](#服务管理命令)
- [访问地址](#访问地址)
- [故障排查](#故障排查)

---

## 🚀 快速启动

### 一键启动所有服务

```bash
cd /Users/lukeding/Desktop/playground/2025/LiveTalking
./start-all.sh
```

### 一键停止所有服务

```bash
cd /Users/lukeding/Desktop/playground/2025/LiveTalking
./stop-all.sh
```

---

## 📚 详细启动步骤

### 方式一：使用管理脚本（推荐）

#### 1. 启动后端服务（后台运行）

```bash
cd /Users/lukeding/Desktop/playground/2025/LiveTalking
./livetalking-daemon.sh start
```

**输出示例：**
```
[2025-01-30 02:00:00] =========================================
[2025-01-30 02:00:00] 🚀 启动 LiveTalking 服务
[2025-01-30 02:00:00] =========================================
[2025-01-30 02:00:00] 📝 配置参数:
[2025-01-30 02:00:00]    - FPS: 25
[2025-01-30 02:00:00]    - 分辨率: 384x384
[2025-01-30 02:00:00]    - Batch Size: 8
[2025-01-30 02:00:00]    - TTS: Edge
[2025-01-30 02:00:00]    - ASR: Lip
[2025-01-30 02:00:00] ✅ 服务启动成功！
```

#### 2. 启动前端开发服务器

```bash
cd /Users/lukeding/Desktop/playground/2025/LiveTalking/frontend/desktop_app
npm run dev
```

**访问地址：** http://localhost:1420

---

### 方式二：手动启动（开发调试用）

#### 步骤 1: 启动 SRS（WebRTC 推流网关）

```bash
cd /Users/lukeding/Desktop/playground/2025/LiveTalking
docker compose up -d srs
```

**验证 SRS 是否启动：**
```bash
docker ps | grep srs
curl http://localhost:8080
```

#### 步骤 2: 设置环境变量

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/src:$(pwd)/src/core:$(pwd)/src/llm:$(pwd)/src/utils:$(pwd)/src/main"
export OMP_NUM_THREADS=8
```

#### 步骤 3: 启动后端服务（前台运行，可看到实时日志）

```bash
cd /Users/lukeding/Desktop/playground/2025/LiveTalking
poetry run python src/main/app.py \
  --transport rtcpush \
  --push_url http://localhost:1985/rtc/v1/whip/?app=live&stream=livestream \
  --model wav2lip \
  --fps 25 \
  -l 8 -m 6 -r 8 \
  --W 384 --H 384 \
  --batch_size 8 \
  --listenport 8010 \
  --avatar_id wav2lip256_avatar1 \
  --tts edge \
  --asr lip
```

#### 步骤 4: 启动前端（新终端窗口）

```bash
cd /Users/lukeding/Desktop/playground/2025/LiveTalking/frontend/desktop_app
npm run dev
```

---

## 🔧 服务管理命令

### 后端服务管理

```bash
# 启动服务（后台）
./livetalking-daemon.sh start

# 停止服务
./livetalking-daemon.sh stop

# 重启服务
./livetalking-daemon.sh restart

# 查看状态
./livetalking-daemon.sh status

# 查看实时日志
./livetalking-daemon.sh logs

# 查看最近的错误
./livetalking-daemon.sh errors
```

### SRS 服务管理

```bash
# 启动 SRS
docker compose up -d srs

# 停止 SRS
docker compose down srs

# 重启 SRS
docker compose restart srs

# 查看 SRS 日志
docker logs -f srs
```

### 查看运行状态

```bash
# 查看后端进程
ps aux | grep "python.*app.py"

# 查看端口占用
lsof -i :8010    # 后端 API
lsof -i :1985    # SRS WHIP
lsof -i :1935    # SRS RTMP
lsof -i :8080    # SRS HTTP
lsof -i :1420    # 前端开发服务器
```

---

## 📱 访问地址

启动成功后，可以通过以下地址访问：

| 服务 | 地址 | 说明 |
|------|------|------|
| **前端应用** | http://localhost:1420 | React 开发服务器 |
| **SRS 控制台** | http://localhost:8080/console/ | SRS 管理界面 |
| **FLV 播放** | http://localhost:8080/live/livestream.flv | 直播流（测试用） |
| **WebRTC 播放** | http://localhost:8080/players/rtc_player.html | WebRTC 播放器 |

---

## 🔍 故障排查

### 问题 1: 后端启动失败

**检查日志：**
```bash
./livetalking-daemon.sh errors
tail -50 logs/livetalking.log
```

**常见原因：**
- 端口 8010 被占用：`lsof -i :8010`
- Python 依赖缺失：`poetry install`
- SRS 未启动：`docker ps | grep srs`

### 问题 2: 前端无法连接后端

**检查后端状态：**
```bash
curl http://localhost:8010/health
```

**检查代理配置：**
```bash
cat vite.config.ts
```

### 问题 3: 视频流卡顿

**使用性能优化脚本：**
```bash
/tmp/apply_optimization.sh
```

或手动调整参数（修改 `livetalking-daemon.sh`）：
- 降低 FPS: 25 → 20
- 降低分辨率: 384 → 256
- 减少 Batch Size: 8 → 4

### 问题 4: SRS 连接失败

**检查 SRS 状态：**
```bash
docker ps | grep srs
curl http://localhost:1985
docker logs srs
```

**重启 SRS：**
```bash
docker compose restart srs
```

### 问题 5: 端口冲突

**查找占用进程：**
```bash
lsof -i :8010
lsof -i :1985
lsof -i :8080
```

**终止占用进程：**
```bash
kill -9 <PID>
```

---

## 📊 性能监控

### 实时监控后端性能

```bash
# 监控 CPU 和内存
watch -n 1 './livetalking-daemon.sh status'

# 监控日志
./livetalking-daemon.sh logs

# 监控 GPU（macOS）
sudo powermetrics --samplers gpu_power -i 1000
```

### 性能优化建议

根据你的设备配置选择优化模式：

| 配置 | FPS | 分辨率 | Batch Size |
|------|-----|--------|------------|
| **推荐模式** | 25 | 384x384 | 8 |
| **极限性能** | 20 | 256x256 | 4 |
| **高质量** | 30 | 450x450 | 12 |

---

## 📝 配置文件位置

| 文件 | 路径 |
|------|------|
| **环境变量** | `.env` |
| **Docker 配置** | `docker-compose.yml` |
| **后端日志** | `logs/livetalking.log` |
| **PID 文件** | `livetalking.pid` |
| **前端配置** | `frontend/desktop_app/vite.config.ts` |

---

## 🎯 下一步

启动成功后：

1. **打开前端**：访问 http://localhost:1420
2. **点击绿色电话按钮**：建立 WebRTC 连接
3. **测试语音识别**：点击麦克风按钮
4. **测试对话**：输入文字或语音说话
5. **调整设置**：点击设置按钮配置参数

---

## 💡 提示

- ✅ 首次启动建议使用 `./start-all.sh` 一键启动
- ✅ 开发时可以使用前台运行查看实时日志
- ✅ 生产环境务必使用 `./livetalking-daemon.sh` 后台运行
- ✅ 定期检查日志文件排查问题
- ✅ 遇到问题先查看 `./livetalking-daemon.sh status`

---

## 🆘 获取帮助

如果遇到问题：

```bash
# 查看完整的帮助信息
./livetalking-daemon.sh
```

或查看项目文档和 GitHub Issues。
