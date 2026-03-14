# 会话进程隔离设计方案

**日期**: 2026-03-14
**作者**: Claude Code
**状态**: 设计阶段

## 一、问题背景

### 1.1 问题描述
当前系统在客户端断开连接后，存在资源未正确释放的问题：
- 前端点击断开连接后，下次连接失败
- 所有 HTTP 接口不可用
- 必须重启整个服务才能恢复

### 1.2 根本原因
通过代码分析发现：
1. `lipreal.py` 中 `infer_thread.join()` 和 `process_thread.join()` **没有超时参数**
2. 线程在等待 `multiprocessing.Queue.get()` 时可能永久阻塞
3. 主线程阻塞导致整个 aiohttp 事件循环停止
4. 所有 API 接口不可用

### 1.3 设计目标
- **进程隔离**：将会话运行在独立子进程中
- **强制清理**：子进程可直接终止，彻底释放资源
- **零阻塞**：主进程不被子进程影响
- **核心不动**：ASR→LLM→TTS 和视频流算法保持不变

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│                  主进程 (aiohttp)                     │
│  ┌──────────────┐         ┌──────────────────┐     │
│  │  HTTP API    │         │  SessionManager  │     │
│  │  /offer      │───────▶│  - 创建会话      │     │
│  │  /destroy    │         │  - 销毁会话      │     │
│  │  /status     │         │  - 监控进程      │     │
│  └──────────────┘         └──────────────────┘     │
│           │                       │                 │
│           │                       ▼                 │
│  ┌─────────────────────────────────────────┐      │
│  │         multiprocessing.Queue            │      │
│  │    (进程间通信 - WebRTC tracks)         │      │
│  └─────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────┘
                        │
                        │ spawn/terminate
                        ▼
┌─────────────────────────────────────────────────────┐
│              子进程 (会话 A)                          │
│  ┌──────────────────────────────────────────┐       │
│  │    SessionProcess (独立进程)              │       │
│  │  - LipReal (渲染/推理)                    │       │
│  │  - WebRTC Tracks                         │       │
│  │  - TTS/ASR/LLM                           │       │
│  │  - AI Model (GPU)                        │       │
│  └──────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────┘
```

### 2.2 修改范围

**可以修改**：
- `src/main/app.py` - 添加 SessionManager、进程管理
- `src/main/app.py` - HumanPlayer 改为从队列读取
- 新增 `src/main/session_process.py` - 子进程入口
- 新增 `src/main/session_manager.py` - 会话管理

**不能修改**（核心算法）：
- `src/core/lipreal.py` - 核心渲染逻辑
- `src/core/lipasr.py` - ASR 逻辑
- `src/core/ttsreal.py` - TTS 逻辑
- `src/core/basereal.py` - 基础逻辑

---

## 三、核心组件设计

### 3.1 SessionProcess（子进程封装）

```python
class SessionProcess:
    """子进程会话的封装"""

    def __init__(self, session_id: str, avatar_id: str, opt):
        self.session_id = session_id
        self.avatar_id = avatar_id
        self.process = None              # multiprocessing.Process
        self.command_queue = None        # 主 → 子：控制命令
        self.audio_queue = None          # 子 → 主：音频帧
        self.video_queue = None          # 子 → 主：视频帧
        self.status = "idle"             # idle, running, stopping, stopped, error
        self.pid = None
        self.start_time = None

    def start(self):
        """启动子进程"""
        self.process = multiprocessing.Process(
            target=session_main,
            args=(self.session_id, self.avatar_id, self.command_queue,
                  self.audio_queue, self.video_queue)
        )
        self.process.start()
        self.pid = self.process.pid
        self.start_time = time.time()

    async def stop(self, timeout=3.0):
        """停止子进程"""
        # 1. 发送 stop 命令
        # 2. 等待优雅退出
        # 3. 超时则 terminate
        # 4. 清理队列
```

### 3.2 SessionManager（会话管理器）

```python
class SessionManager:
    """会话生命周期管理"""

    def __init__(self, max_sessions=10):
        self.sessions: Dict[str, SessionProcess] = {}
        self.lock = asyncio.Lock()
        self.max_sessions = max_sessions

    async def create_session(self, session_id: str, avatar_id: str, opt):
        """创建新会话"""
        async with self.lock:
            if len(self.sessions) >= self.max_sessions:
                raise Exception("Max session limit reached")

            session = SessionProcess(session_id, avatar_id, opt)
            session.start()
            self.sessions[session_id] = session

            # 等待初始化完成
            await session.wait_ready(timeout=30.0)
            return session

    async def destroy_session(self, session_id: str, force=False):
        """销毁会话"""
        async with self.lock:
            if session_id not in self.sessions:
                return

            session = self.sessions[session_id]
            await session.stop()
            del self.sessions[session_id]

    async def get_session(self, session_id: str):
        """获取会话"""
        return self.sessions.get(session_id)

    async def monitor_sessions(self):
        """后台监控任务"""
        while True:
            await asyncio.sleep(10)
            async with self.lock:
                for session_id, session in list(self.sessions.items()):
                    if not session.is_alive():
                        logger.warning(f"检测到死进程: {session_id}")
                        await self.destroy_session(session_id, force=True)
```

### 3.3 HumanPlayer 修改

```python
class HumanPlayer:
    """WebRTC 媒体流播放器 - 从队列读取版本"""

    def __init__(self, session_process: SessionProcess):
        self.session = session_process
        self.audio_queue = session.audio_queue
        self.video_queue = session.video_queue

    async def audio_track(self):
        """音频轨道 - 从队列读取"""
        while True:
            frame = await asyncio.get_event_loop().run_in_executor(
                None, self.audio_queue.get
            )
            if frame is None:  # 结束信号
                break
            yield frame

    async def video_track(self):
        """视频轨道 - 从队列读取"""
        while True:
            frame = await asyncio.get_event_loop().run_in_executor(
                None, self.video_queue.get
            )
            if frame is None:  # 结束信号
                break
            yield frame
```

### 3.4 子进程入口

```python
def session_main(session_id: str, avatar_id: str,
                 command_queue: multiprocessing.Queue,
                 audio_queue: multiprocessing.Queue,
                 video_queue: multiprocessing.Queue):
    """子进程主函数"""

    # 1. 初始化 LipReal（原有逻辑不变）
    nerfreal = build_nerfreal(session_id, avatar_id)

    # 2. 启动渲染线程（原有逻辑不变）
    nerfreal.render(...)

    # 3. 将 WebRTC tracks 发送到队列
    while not quit_event.is_set():
        audio_frame = nerfreal.audio_track.recv()
        video_frame = nerfreal.video_track.recv()

        audio_queue.put(audio_frame)
        video_queue.put(video_frame)

    # 4. 清理
    nerfreal.stop_all_threads()
```

---

## 四、API 接口设计

### 4.1 修改 /offer 接口

```python
@app.route('/offer', methods=['POST'])
async def offer(request):
    """创建 WebRTC 会话"""

    # 原有验证逻辑...

    # 创建会话进程
    session = await session_manager.create_session(sessionid, avatar_id, opt)

    # 创建 WebRTC 连接（原逻辑）
    pc = RTCPeerConnection(...)
    player = HumanPlayer(session)  # 传入 SessionProcess

    # 添加轨道
    pc.addTrack(player.audio)
    pc.addTrack(player.video)

    # 返回
    return web.Response(
        text=json.dumps({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "sessionid": sessionid,
            "destroy_url": f"/api/session/{sessionid}/destroy",
            "code": 0
        })
    )
```

### 4.2 新增 /destroy 接口

```python
@app.route('/api/session/<session_id>/destroy', methods=['POST'])
async def destroy_session(request):
    """主动销毁会话"""

    session_id = request.match_info['session_id']

    # 验证会话存在
    session = await session_manager.get_session(session_id)
    if not session:
        return web.Response(
            text=json.dumps({"code": -1, "msg": "Session not found"}),
            status=404
        )

    # 销毁会话
    await session_manager.destroy_session(session_id)

    return web.Response(
        text=json.dumps({"code": 0, "msg": "Session destroyed"})
    )
```

### 4.3 新增 /status 接口（可选）

```python
@app.route('/api/session/<session_id>/status', methods=['GET'])
async def session_status(request):
    """查询会话状态"""

    session_id = request.match_info['session_id']
    session = await session_manager.get_session(session_id)

    if not session:
        return web.Response(
            text=json.dumps({"code": -1, "msg": "Session not found"}),
            status=404
        )

    return web.Response(
        text=json.dumps({
            "session_id": session_id,
            "status": session.status,
            "pid": session.pid,
            "uptime": time.time() - session.start_time if session.start_time else 0,
            "code": 0
        })
    )
```

---

## 五、进程通信机制

### 5.1 队列设计

```
主进程 → 子进程:
├── command_queue (multiprocessing.Queue)
│   ├── {"action": "start"}      # 启动渲染
│   ├── {"action": "stop"}       # 停止渲染
│   └── {"action": "config", "data": {...}}  # 更新配置

子进程 → 主进程:
├── audio_queue (multiprocessing.Queue)
│   └── AudioFrame 对象
├── video_queue (multiprocessing.Queue)
│   └── VideoFrame 对象
└── status_queue (multiprocessing.Queue)
    └── {"status": "ready"}  # 初始化完成信号
```

### 5.2 序列化处理

由于 multiprocessing.Queue 需要序列化，使用以下策略：

```python
# 音频帧：转换为 bytes
audio_bytes = frame.to_bytes()

# 视频帧：转换为 bytes (使用 av 库)
video_bytes = frame.to_bytes()

# 接收端：重建 Frame
audio_frame = AudioFrame.from_bytes(audio_bytes)
video_frame = VideoFrame.from_bytes(video_bytes)
```

---

## 六、生命周期管理

### 6.1 状态转换

```
         spawn
   [idle] ──────▶ [starting]
        │             │
        │          ready
        │             │
        │             ▼
        │         [running]
        │             │
        │             │ stop/timeout/crash
        │             ▼
        │         [stopping]
        │             │
        │        terminated
        │             │
        └────────▶ [stopped]
                      │
                      │ cleanup
                      ▼
                  [dead]
```

### 6.2 清理流程

```python
async def stop(self, timeout=3.0):
    """停止子进程的完整流程"""

    # 步骤1: 发送停止命令
    self.command_queue.put({"action": "stop"})

    # 步骤2: 等待优雅退出
    try:
        await asyncio.wait_for(
            self.process.join_async(),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"会话 {self.session_id} 优雅退出超时")

    # 步骤3: 强制终止
    if self.process.is_alive():
        self.process.terminate()
        await asyncio.sleep(2)
        if self.process.is_alive():
            self.process.kill()

    # 步骤4: 清理队列
    self.command_queue.close()
    self.audio_queue.close()
    self.video_queue.close()

    # 步骤5: 等待进程结束
    self.process.join(timeout=5)
    self.status = "stopped"
```

### 6.3 僵尸进程检测

```python
async def monitor_sessions(self):
    """后台监控任务"""
    while True:
        await asyncio.sleep(10)

        async with self.lock:
            for session_id, session in list(self.sessions.items()):

                # 检查进程是否存活
                if not session.process.is_alive():
                    logger.warning(f"检测到死进程: {session_id} (exitcode={session.process.exitcode})")
                    await self.destroy_session(session_id, force=True)
                    continue

                # 检查进程是否僵尸（无活动）
                idle_time = time.time() - session.last_activity
                if idle_time > 300:  # 5分钟无活动
                    logger.warning(f"会话 {session_id} 超时，清理")
                    await self.destroy_session(session_id)
```

---

## 七、错误处理与容错

### 7.1 异常场景

| 场景 | 处理方式 |
|------|---------|
| 子进程初始化超时 | terminate，返回错误给客户端 |
| 子进程运行时崩溃 | monitor 检测，清理残留资源 |
| 队列阻塞 | 使用超时 + 强制终止 |
| GPU 内存不足 | 提前检测，返回错误 |
| 进程无法终止 | 使用 kill -9 |

### 7.2 资源清理清单

**子进程退出时**：
- ✅ GPU 内存 (`torch.cuda.empty_cache()`)
- ✅ 所有线程 (`thread.join(timeout)`)
- ✅ 所有队列 (`queue.close()`)
- ✅ WebRTC connections (`pc.close()`)
- ✅ WebSocket 连接 (TTS 连接池)
- ✅ 文件句柄

**主进程清理**：
- ✅ 进程对象 (`process.join()`)
- ✅ 队列对象 (`queue.close()`)
- ✅ SessionManager 映射 (`del sessions[id]`)
- ✅ WebRTC PeerConnection (`pc.close()`)

---

## 八、实施计划

### 第一阶段：核心框架（必须）

- [ ] 创建 `SessionProcess` 类
- [ ] 实现 `SessionManager` 基础功能
- [ ] 编写子进程入口 `session_main()`
- [ ] 实现进程间通信队列

### 第二阶段：集成验证（必须）

- [ ] 修改 `/offer` 接口使用进程隔离
- [ ] 修改 `HumanPlayer` 从队列读取
- [ ] 实现 `/destroy` 接口
- [ ] 前端集成 `destroy` 调用
- [ ] 单会话功能测试

### 第三阶段：完善功能（重要）

- [ ] 进程监控和自动清理
- [ ] 会话状态查询接口
- [ ] 超时保护机制
- [ ] 多会话压力测试

### 第四阶段：优化增强（可选）

- [ ] 进程资源限制 (memory_limit)
- [ ] 崩溃重启机制
- [ ] 性能监控指标
- [ ] 优雅降级策略

### 8.1 风险控制

**高风险点**：
- multiprocessing.Queue 与 aiortc 集成
- GPU 资源在子进程中的分配
- 进程间数据传输序列化开销

**降级方案**：
保留原有代码路径，通过配置开关控制：
```python
USE_PROCESS_ISOLATION = os.getenv("USE_PROCESS_ISOLATION", "true") == "true"
```

---

## 九、前端集成

### 9.1 断开连接时调用 destroy

```javascript
// 断开连接函数
async function disconnect() {
    // 1. 关闭 WebRTC 连接
    if (pc) {
        pc.close();
        pc = null;
    }

    // 2. 调用 destroy 接口
    if (sessionId) {
        try {
            await fetch(`/api/session/${sessionId}/destroy`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            });
        } catch (e) {
            console.error('Destroy session failed:', e);
        }
        sessionId = null;
    }

    // 3. 更新 UI
    updateConnectionStatus('disconnected');
}
```

### 9.2 页面关闭前清理

```javascript
// 监听页面关闭
window.addEventListener('beforeunload', () => {
    if (sessionId) {
        // 使用 sendBeacon 确保请求发送
        navigator.sendBeacon(
            `/api/session/${sessionId}/destroy`,
            JSON.stringify({})
        );
    }
});
```

---

## 十、测试计划

### 10.1 功能测试

- [ ] 创建会话成功
- [ ] 正常音视频通信
- [ ] 主动销毁会话
- [ ] 断线后自动清理
- [ ] 多会话并发

### 10.2 压力测试

- [ ] 连续创建/销毁 100 次会话
- [ ] 10 个并发会话
- [ ] 长时间运行稳定性（24小时）

### 10.3 异常测试

- [ ] 子进程崩溃恢复
- [ ] GPU 内存不足处理
- [ ] 网络中断处理

---

## 十一、性能影响评估

### 11.1 优势

- ✅ 彻底隔离，单个会话崩溃不影响其他会话
- ✅ 强制清理，无资源泄漏风险
- ✅ 可监控进程状态，便于调试

### 11.2 劣势

- ❌ 进程创建开销（~100-200ms）
- ❌ 进程间通信序列化开销
- ❌ 内存占用增加（每个进程独立 Python 解释器）

### 11.3 优化措施

- 进程池预创建（减少创建开销）
- 共享内存（减少序列化开销）
- 半结构化数据传输（优化序列化）

---

## 十二、配置选项

```bash
# 环境变量配置
USE_PROCESS_ISOLATION=true          # 是否启用进程隔离
MAX_SESSIONS=10                     # 最大会话数
SESSION_IDLE_TIMEOUT=300           # 会话空闲超时（秒）
SESSION_STOP_TIMEOUT=3             # 会话停止超时（秒）
PROCESS_MEMORY_LIMIT=2147483648    # 进程内存限制（2GB）
```

---

## 十三、回滚方案

如果进程隔离方案出现问题，可通过以下方式快速回滚：

```bash
# 方式1: 环境变量
export USE_PROCESS_ISOLATION=false

# 方式2: 配置文件
# config.py
USE_PROCESS_ISOLATION = False

# 方式3: 代码回滚
git revert <commit-hash>
```

---

## 十四、总结

本设计方案通过进程隔离彻底解决了当前系统的资源泄漏和阻塞问题：

1. **根本解决**：子进程可强制终止，无阻塞风险
2. **核心不变**：ASR→LLM→TTS 和视频流算法保持不变
3. **易于维护**：清晰的进程边界，便于调试
4. **可扩展性**：支持未来扩展（进程池、资源限制等）

预计实施周期：**2-3 天**
预计风险等级：**中等**（主要是进程间通信集成）
