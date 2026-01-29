# LiveTalking 快速启动卡片

## 🚀 一键启动

```bash
cd /Users/lukeding/Desktop/playground/2025/LiveTalking

# 启动所有服务
./start-all.sh

# 停止所有服务
./stop-all.sh
```

---

## 🔧 核心命令

| 命令 | 说明 |
|------|------|
| `./livetalking-daemon.sh start` | 启动后端（后台） |
| `./livetalking-daemon.sh stop` | 停止后端 |
| `./livetalking-daemon.sh restart` | 重启后端 |
| `./livetalking-daemon.sh status` | 查看状态 |
| `./livetalking-daemon.sh logs` | 查看日志 |
| `./livetalking-daemon.sh errors` | 查看错误 |

---

## 📍 访问地址

- **前端**: http://localhost:1420
- **SRS 控制台**: http://localhost:8080/console/
- **直播流**: http://localhost:8080/live/livestream.flv

---

## 📂 文件位置

| 文件 | 说明 |
|------|------|
| `livetalking-daemon.sh` | 服务管理脚本 |
| `start-all.sh` | 一键启动脚本 |
| `stop-all.sh` | 一键停止脚本 |
| `SERVICE_GUIDE.md` | 详细文档 |
| `logs/livetalking.log` | 后端日志 |
| `livetalking.pid` | 进程 ID 文件 |

---

## 💡 快速提示

1. **首次启动** → 使用 `./start-all.sh`
2. **开发调试** → 前台运行查看日志
3. **生产环境** → 使用 daemon 后台运行
4. **遇到问题** → 先执行 `./livetalking-daemon.sh status`

---

## 🎯 当前配置

- **FPS**: 25
- **分辨率**: 384x384
- **Batch Size**: 8
- **TTS**: Edge (免费)
- **ASR**: Lip (端到端)
- **端口**: 8010
- **传输**: RTCPush (WHIP)

---

## ✅ 服务状态检查清单

启动后确认：

- [ ] SRS 容器运行中 (`docker ps`)
- [ ] 后端服务运行中 (`./livetalking-daemon.sh status`)
- [ ] 前端开发服务器运行 (http://localhost:1420)
- [ ] 可以访问 SRS 控制台 (http://localhost:8080/console/)
- [ ] 日志无错误 (`./livetalking-daemon.sh errors`)

---

生成时间: 2025-01-30
项目路径: /Users/lukeding/Desktop/playground/2025/LiveTalking
