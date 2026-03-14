# Session Process Isolation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将会话运行在独立子进程中，通过进程隔离彻底解决资源泄漏和阻塞问题，同时保持核心算法（ASR→LLM→TTS、视频流）不变。

**Architecture:** 主进程运行 aiohttp 和 SessionManager，每个会话在独立的子进程中运行 LipReal。进程间通过 multiprocessing.Queue 通信：主进程发送控制命令，子进程发送音视频帧。子进程可被强制终止，确保资源释放。

**Tech Stack:** multiprocessing, asyncio, aiortc, aiohttp, torch

---

## 核心约束

**不能修改的文件（核心算法）：**
- `src/core/lipreal.py` - 视频渲染逻辑
- `src/core/lipasr.py` - ASR 逻辑
- `src/core/ttsreal.py` - TTS 逻辑
- `src/core/basereal.py` - 基础逻辑

**可以修改的文件：**
- `src/main/app.py` - 主应用入口
- 新增 `src/main/session_process.py` - 会话进程封装
- 新增 `src/main/session_manager.py` - 会话管理器
- 前端断开连接逻辑

---

## Task 1: 创建 SessionProcess 类

**Files:**
- Create: `src/main/session_process.py`

**Step 1: 创建文件框架**

```python
# src/main/session_process.py
"""会话进程封装 - 每个会话运行在独立子进程中"""

import asyncio
import multiprocessing
import queue
import time
import logging
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    """会话状态"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class SessionProcess:
    """子进程会话的封装"""

    def __init__(self, session_id: str, avatar_id: str, opt: Any):
        self.session_id = session_id
        self.avatar_id = avatar_id
        self.opt = opt

        # 进程相关
        self.process: Optional[multiprocessing.Process] = None
        self.pid: Optional[int] = None

        # 进程间通信队列
        self.command_queue: Optional[multiprocessing.Queue] = None
        self.audio_queue: Optional[multiprocessing.Queue] = None
        self.video_queue: Optional[multiprocessing.Queue] = None
        self.status_queue: Optional[multiprocessing.Queue] = None

        # 状态
        self.status = SessionStatus.IDLE
        self.start_time: Optional[float] = None
        self.last_activity: Optional[float] = None

        logger.info(f"[SessionProcess] Created session {session_id} for avatar {avatar_id}")

    def start(self) -> bool:
        """启动子进程"""
        try:
            # 创建队列
            self.command_queue = multiprocessing.Queue(maxsize=100)
            self.audio_queue = multiprocessing.Queue(maxsize=100)
            self.video_queue = multiprocessing.Queue(maxsize=100)
            self.status_queue = multiprocessing.Queue(maxsize=10)

            # 创建并启动进程
            self.process = multiprocessing.Process(
                target=_session_main,
                args=(
                    self.session_id,
                    self.avatar_id,
                    self.opt,
                    self.command_queue,
                    self.audio_queue,
                    self.video_queue,
                    self.status_queue
                ),
                daemon=False
            )

            self.process.start()
            self.pid = self.process.pid
            self.start_time = time.time()
            self.last_activity = time.time()
            self.status = SessionStatus.STARTING

            logger.info(f"[SessionProcess] Started session {self.session_id} (pid={self.pid})")
            return True

        except Exception as e:
            logger.error(f"[SessionProcess] Failed to start session {self.session_id}: {e}")
            self.status = SessionStatus.ERROR
            return False

    async def wait_ready(self, timeout: float = 30.0) -> bool:
        """等待会话初始化完成"""
        try:
            loop = asyncio.get_event_loop()
            msg = await asyncio.wait_for(
                loop.run_in_executor(None, self.status_queue.get),
                timeout=timeout
            )

            if msg.get("status") == "ready":
                self.status = SessionStatus.RUNNING
                logger.info(f"[SessionProcess] Session {self.session_id} is ready")
                return True
            else:
                logger.error(f"[SessionProcess] Session {self.session_id} failed to initialize: {msg}")
                self.status = SessionStatus.ERROR
                return False

        except asyncio.TimeoutError:
            logger.error(f"[SessionProcess] Session {self.session_id} initialization timeout")
            self.status = SessionStatus.ERROR
            return False
        except Exception as e:
            logger.error(f"[SessionProcess] Error waiting for session {self.session_id}: {e}")
            self.status = SessionStatus.ERROR
            return False

    async def stop(self, timeout: float = 3.0) -> bool:
        """停止子进程"""
        if self.status in [SessionStatus.STOPPED, SessionStatus.IDLE]:
            return True

        self.status = SessionStatus.STOPPING
        logger.info(f"[SessionProcess] Stopping session {self.session_id}")

        try:
            # 步骤1: 发送停止命令
            if self.command_queue:
                try:
                    self.command_queue.put({"action": "stop"}, block=False)
                except:
                    pass

            # 步骤2: 等待优雅退出
            if self.process:
                try:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, self.process.join
                        ),
                        timeout=timeout
                    )
                    logger.info(f"[SessionProcess] Session {self.session_id} stopped gracefully")
                except asyncio.TimeoutError:
                    logger.warning(f"[SessionProcess] Session {self.session_id} stop timeout, terminating")

                    # 步骤3: 强制终止
                    if self.process.is_alive():
                        self.process.terminate()
                        await asyncio.sleep(2)

                        if self.process.is_alive():
                            logger.warning(f"[SessionProcess] Session {self.session_id} terminate failed, killing")
                            self.process.kill()
                            await asyncio.sleep(1)

            # 步骤4: 清理队列
            self._cleanup_queues()

            # 步骤5: 等待进程结束
            if self.process:
                self.process.join(timeout=5)

            self.status = SessionStatus.STOPPED
            logger.info(f"[SessionProcess] Session {self.session_id} stopped")
            return True

        except Exception as e:
            logger.error(f"[SessionProcess] Error stopping session {self.session_id}: {e}")
            self.status = SessionStatus.ERROR
            return False

    def _cleanup_queues(self):
        """清理队列"""
        for q in [self.command_queue, self.audio_queue, self.video_queue, self.status_queue]:
            if q:
                try:
                    q.close()
                except:
                    pass

    def is_alive(self) -> bool:
        """检查进程是否存活"""
        return self.process and self.process.is_alive()

    def update_activity(self):
        """更新活动时间"""
        self.last_activity = time.time()


def _session_main(session_id: str, avatar_id: str, opt: Any,
                  command_queue: multiprocessing.Queue,
                  audio_queue: multiprocessing.Queue,
                  video_queue: multiprocessing.Queue,
                  status_queue: multiprocessing.Queue):
    """
    子进程主函数

    这个函数在独立的子进程中运行，负责：
    1. 初始化 LipReal
    2. 启动渲染线程
    3. 将音视频帧发送到队列
    4. 响应控制命令
    """
    import sys
    import os

    # 设置进程名称
    try:
        import setproctitle
        setproctitle.setproctitle(f"livetalking-session-{session_id}")
    except:
        pass

    logger.info(f"[Session-{session_id}] Process started (pid={os.getpid()})")

    try:
        # 导入必要的模块（在子进程中）
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from core.lipreal import LipReal

        # 初始化 LipReal
        nerfreal = build_nerfreal_subprocess(session_id, avatar_id, opt)
        nerfreal.sessionid = session_id

        logger.info(f"[Session-{session_id}] LipReal initialized")

        # 发送就绪信号
        status_queue.put({"status": "ready"})

        # TODO: 启动渲染和队列传输
        # 这部分在后续任务中实现

    except Exception as e:
        logger.error(f"[Session-{session_id}] Error in session_main: {e}")
        import traceback
        logger.error(traceback.format_exc())
        status_queue.put({"status": "error", "message": str(e)})
    finally:
        logger.info(f"[Session-{session_id}] Process exiting")


def build_nerfreal_subprocess(session_id: str, avatar_id: str, opt: Any):
    """在子进程中构建 LipReal 实例"""
    from core.lipreal import LipReal, load_model, load_avatar

    # 加载模型（全局单例，只加载一次）
    if not hasattr(build_nerfreal_subprocess, '_model'):
        model_path = f"./models/wav2lip{opt.W if hasattr(opt, 'W') else 384}.pth"
        build_nerfreal_subprocess._model = load_model(model_path)
        logger.info(f"[Session-{session_id}] Model loaded")

    model = build_nerfreal_subprocess._model

    # 加载 avatar
    avatar = load_avatar(avatar_id)
    logger.info(f"[Session-{session_id}] Avatar loaded: {avatar_id}")

    # 创建 LipReal 实例
    nerfreal = LipReal(opt, model, avatar)

    return nerfreal
```

**Step 2: 提交创建文件**

```bash
git add src/main/session_process.py
git commit -m "feat(session-isolation): create SessionProcess class

- 添加 SessionProcess 类封装子进程会话
- 实现进程启动、停止、等待就绪逻辑
- 定义会话状态枚举
- 添加子进程主函数框架
"
```

---

## Task 2: 创建 SessionManager 类

**Files:**
- Create: `src/main/session_manager.py`

**Step 1: 创建 SessionManager 类**

```python
# src/main/session_manager.py
"""会话管理器 - 管理所有会话进程的生命周期"""

import asyncio
import logging
import time
from typing import Dict, Optional
from session_process import SessionProcess, SessionStatus

logger = logging.getLogger(__name__)


class SessionManager:
    """会话生命周期管理器"""

    def __init__(self, max_sessions: int = 10):
        self.sessions: Dict[str, SessionProcess] = {}
        self.lock = asyncio.Lock()
        self.max_sessions = max_sessions
        self._monitor_task: Optional[asyncio.Task] = None

        logger.info(f"[SessionManager] Initialized with max_sessions={max_sessions}")

    async def create_session(self, session_id: str, avatar_id: str, opt) -> Optional[SessionProcess]:
        """创建新会话"""
        async with self.lock:
            # 检查会话数量限制
            if len(self.sessions) >= self.max_sessions:
                logger.warning(f"[SessionManager] Max session limit reached: {len(self.sessions)}")
                return None

            # 检查会话是否已存在
            if session_id in self.sessions:
                logger.warning(f"[SessionManager] Session {session_id} already exists")
                return None

            # 创建会话
            session = SessionProcess(session_id, avatar_id, opt)

            if not session.start():
                logger.error(f"[SessionManager] Failed to start session {session_id}")
                return None

            # 等待就绪
            if not await session.wait_ready(timeout=30.0):
                logger.error(f"[SessionManager] Session {session_id} failed to initialize")
                await session.stop(timeout=5.0)
                return None

            self.sessions[session_id] = session
            logger.info(f"[SessionManager] Session {session_id} created and ready")
            return session

    async def destroy_session(self, session_id: str, force: bool = False) -> bool:
        """销毁会话"""
        async with self.lock:
            if session_id not in self.sessions:
                logger.warning(f"[SessionManager] Session {session_id} not found")
                return False

            session = self.sessions[session_id]

            logger.info(f"[SessionManager] Destroying session {session_id} (force={force})")

            if force:
                # 强制销毁：直接终止
                if session.process and session.process.is_alive():
                    session.process.terminate()
                    await asyncio.sleep(1)
                    if session.process.is_alive():
                        session.process.kill()
            else:
                # 正常销毁
                await session.stop(timeout=3.0)

            session._cleanup_queues()

            del self.sessions[session_id]
            logger.info(f"[SessionManager] Session {session_id} destroyed")
            return True

    async def get_session(self, session_id: str) -> Optional[SessionProcess]:
        """获取会话"""
        return self.sessions.get(session_id)

    def has_session(self, session_id: str) -> bool:
        """检查会话是否存在"""
        return session_id in self.sessions

    def get_session_count(self) -> int:
        """获取会话数量"""
        return len(self.sessions)

    async def monitor_sessions(self):
        """后台监控任务 - 检测并清理死进程"""
        logger.info("[SessionManager] Starting monitor task")

        while True:
            try:
                await asyncio.sleep(10)

                async with self.lock:
                    dead_sessions = []

                    for session_id, session in list(self.sessions.items()):
                        # 检查进程是否存活
                        if not session.is_alive():
                            logger.warning(
                                f"[SessionManager] Detected dead process: {session_id} "
                                f"(exitcode={session.process.exitcode if session.process else 'N/A'})"
                            )
                            dead_sessions.append(session_id)
                            continue

                        # 检查空闲超时
                        idle_time = time.time() - session.last_activity
                        if idle_time > 300:  # 5分钟无活动
                            logger.warning(f"[SessionManager] Session {session_id} idle timeout ({idle_time:.0f}s)")
                            dead_sessions.append(session_id)

                    # 清理死会话
                    for session_id in dead_sessions:
                        await self.destroy_session(session_id, force=True)

            except asyncio.CancelledError:
                logger.info("[SessionManager] Monitor task cancelled")
                break
            except Exception as e:
                logger.error(f"[SessionManager] Monitor task error: {e}")

    async def start_monitor(self):
        """启动监控任务"""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self.monitor_sessions())

    async def stop_monitor(self):
        """停止监控任务"""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def destroy_all(self):
        """销毁所有会话"""
        logger.info("[SessionManager] Destroying all sessions")

        async with self.lock:
            session_ids = list(self.sessions.keys())

            for session_id in session_ids:
                await self.destroy_session(session_id, force=True)

        logger.info("[SessionManager] All sessions destroyed")
```

**Step 2: 提交创建文件**

```bash
git add src/main/session_manager.py
git commit -m "feat(session-isolation): create SessionManager class

- 实现会话创建、销毁、查询逻辑
- 添加后台监控任务检测死进程
- 支持会话数量限制
- 实现空闲超时清理
"
```

---

## Task 3: 修改子进程主函数实现帧传输

**Files:**
- Modify: `src/main/session_process.py` (修改 `_session_main` 函数)

**Step 1: 实现音视频帧传输到队列**

在 `src/main/session_process.py` 中，替换 `TODO` 部分：

```python
def _session_main(session_id: str, avatar_id: str, opt: Any,
                  command_queue: multiprocessing.Queue,
                  audio_queue: multiprocessing.Queue,
                  video_queue: multiprocessing.Queue,
                  status_queue: multiprocessing.Queue):
    """子进程主函数"""
    import sys
    import os
    import numpy as np
    from av import AudioFrame, VideoFrame
    from threading import Event

    # 设置进程名称
    try:
        import setproctitle
        setproctitle.setproctitle(f"livetalking-session-{session_id}")
    except:
        pass

    logger.info(f"[Session-{session_id}] Process started (pid={os.getpid()})")

    quit_event = Event()

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from core.lipreal import LipReal

        # 初始化 LipReal
        nerfreal = build_nerfreal_subprocess(session_id, avatar_id, opt)
        nerfreal.sessionid = session_id

        logger.info(f"[Session-{session_id}] LipReal initialized")

        # 创建用于传输的队列（从 nerfreal 获取）
        # 我们需要访问 nerfreal 的音视频轨道
        nerfreal.render(quit_event, loop=None, audio_track=None, video_track=None)

        # 发送就绪信号
        status_queue.put({"status": "ready"})

        # 帧传输循环
        logger.info(f"[Session-{session_id}] Starting frame transfer loop")

        while not quit_event.is_set():
            # 检查控制命令
            try:
                cmd = command_queue.get(block=False)
                if cmd.get("action") == "stop":
                    logger.info(f"[Session-{session_id}] Received stop command")
                    break
            except:
                pass

            # 从 nerfreal 获取音视频帧
            # 注意：这里需要访问 nerfreal 的轨道
            # 暂时使用占位符，后续任务中实现
            await asyncio.sleep(0.02)  # 50fps

        logger.info(f"[Session-{session_id}] Frame transfer loop ended")

    except Exception as e:
        logger.error(f"[Session-{session_id}] Error in session_main: {e}")
        import traceback
        logger.error(traceback.format_exc())
        status_queue.put({"status": "error", "message": str(e)})
    finally:
        # 清理
        logger.info(f"[Session-{session_id}] Cleaning up")
        quit_event.set()

        if 'nerfreal' in locals():
            try:
                nerfreal.stop_all_threads()
            except:
                pass

        # 发送结束信号
        try:
            audio_queue.put(None)
            video_queue.put(None)
        except:
            pass

        logger.info(f"[Session-{session_id}] Process exiting")
```

**Step 2: 提交修改**

```bash
git add src/main/session_process.py
git commit -m "feat(session-isolation): implement frame transfer in session_main

- 添加控制命令监听
- 实现音视频帧传输循环
- 添加清理逻辑
"
```

---

## Task 4: 创建 QueueMediaTrack 用于队列传输

**Files:**
- Create: `src/main/queue_track.py`

**Step 1: 创建队列轨道类**

```python
# src/main/queue_track.py
"""从 multiprocessing.Queue 读取的 WebRTC 媒体轨道"""

import asyncio
import logging
from av import AudioFrame, VideoFrame
from aiortc import MediaStreamTrack
from typing import Optional
import multiprocessing

logger = logging.getLogger(__name__)


class QueueAudioTrack(MediaStreamTrack):
    """从队列读取音频的 WebRTC 轨道"""

    def __init__(self, queue: multiprocessing.Queue, session_id: str):
        super().__init__()
        self.queue = queue
        self.session_id = session_id
        self._timestamp = 0
        self._stopped = False

        logger.info(f"[QueueAudioTrack] Created for session {session_id}")

    async def recv(self):
        """接收下一帧"""
        if self._stopped:
            raise StopIteration

        try:
            # 从队列获取音频帧（带超时）
            frame = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.queue.get(timeout=1.0)
            )

            if frame is None:  # 结束信号
                logger.info(f"[QueueAudioTrack] Session {self.session_id} received end signal")
                self._stopped = True
                raise StopIteration

            # 转换为 aiortc AudioFrame
            if isinstance(frame, AudioFrame):
                self._timestamp += frame.samples
                frame.pts = self._timestamp
                frame.time_base = "1/48000"  # 48kHz
                return frame
            else:
                # 如果是 numpy 数组，转换为 AudioFrame
                import numpy as np
                audio_frame = AudioFrame.from_ndarray(frame, format='s16', layout='mono')
                self._timestamp += audio_frame.samples
                audio_frame.pts = self._timestamp
                audio_frame.time_base = "1/48000"
                return audio_frame

        except Exception as e:
            logger.error(f"[QueueAudioTrack] Error receiving frame: {e}")
            # 返回静音帧避免卡顿
            return AudioFrame(format='s16', layout='mono', samples=960)


class QueueVideoTrack(MediaStreamTrack):
    """从队列读取视频的 WebRTC 轨道"""

    def __init__(self, queue: multiprocessing.Queue, session_id: str):
        super().__init__()
        self.queue = queue
        self.session_id = session_id
        self._timestamp = 0
        self._stopped = False

        logger.info(f"[QueueVideoTrack] Created for session {session_id}")

    async def recv(self):
        """接收下一帧"""
        if self._stopped:
            raise StopIteration

        try:
            # 从队列获取视频帧（带超时）
            frame = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.queue.get(timeout=1.0)
            )

            if frame is None:  # 结束信号
                logger.info(f"[QueueVideoTrack] Session {self.session_id} received end signal")
                self._stopped = True
                raise StopIteration

            # 转换为 aiortc VideoFrame
            if isinstance(frame, VideoFrame):
                self._timestamp += 1
                frame.pts = self._timestamp
                frame.time_base = "1/90000"  # 90kHz (RTP 标准)
                return frame
            else:
                # 如果是 numpy 数组，转换为 VideoFrame
                import numpy as np
                video_frame = VideoFrame.from_ndarray(frame, format='bgr24')
                self._timestamp += 1
                video_frame.pts = self._timestamp
                video_frame.time_base = "1/90000"
                return video_frame

        except Exception as e:
            logger.error(f"[QueueVideoTrack] Error receiving frame: {e}")
            # 返回上一帧或黑帧避免卡顿
            raise StopIteration
```

**Step 2: 提交创建文件**

```bash
git add src/main/queue_track.py
git commit -m "feat(session-isolation): create QueueMediaTrack classes

- 添加 QueueAudioTrack 从队列读取音频
- 添加 QueueVideoTrack 从队列读取视频
- 实现超时和错误处理
- 支持结束信号
"
```

---

## Task 5: 修改 app.py 集成 SessionManager

**Files:**
- Modify: `src/main/app.py`

**Step 1: 在 app.py 顶部添加导入**

在 `src/main/app.py` 的导入区域添加：

```python
# 在现有导入后添加
from session_manager import SessionManager
from queue_track import QueueAudioTrack, QueueVideoTrack
```

**Step 2: 初始化 SessionManager**

在 `src/main/app.py` 中，找到 nerfreals 初始化的位置，添加：

```python
# 在 nerfreals = {} 之后添加
session_manager = SessionManager(max_sessions=opt.max_session)
logger.info("[APP] SessionManager initialized")
```

**Step 3: 在 startup 时启动监控**

找到 `on_startup` 函数，在现有监控任务后添加：

```python
# 启动会话监控
asyncio.create_task(session_manager.start_monitor())
logger.info("[APP] Session monitor started")
```

**Step 4: 提交修改**

```bash
git add src/main/app.py
git commit -m "feat(session-isolation): integrate SessionManager into app

- 添加 SessionManager 导入和初始化
- 在启动时启动会话监控任务
"
```

---

## Task 6: 修改 /offer 接口使用进程隔离

**Files:**
- Modify: `src/main/app.py`

**Step 1: 修改 offer 函数创建会话**

找到 `async def offer(request):` 函数，在创建 nerfreal 的部分修改为：

```python
# 原代码（注释掉）:
# nerfreal = await asyncio.wait_for(
#     asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid, avatar_id),
#     timeout=30.0
# )

# 新代码: 使用 SessionManager 创建会话
session = await session_manager.create_session(sessionid, avatar_id, opt)
if not session:
    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": -1, "msg": "Failed to create session"}),
        status=500
    )
logger.info(f"[OFFER] Session {sessionid} created successfully")
```

**Step 2: 修改 HumanPlayer 创建**

找到创建 HumanPlayer 的部分，修改为：

```python
# 原代码:
# player = HumanPlayer(nerfreals[sessionid])

# 新代码: 使用队列轨道
audio_track = QueueAudioTrack(session.audio_queue, sessionid)
video_track = QueueVideoTrack(session.video_queue, sessionid)

# 创建简化的 player（用于后续清理）
player = SimplePlayer(session, audio_track, video_track)
```

**Step 3: 添加 SimplePlayer 类**

在 `src/main/app.py` 中添加：

```python
class SimplePlayer:
    """简化的播放器，用于保存会话引用"""
    def __init__(self, session, audio_track, video_track):
        self.session = session
        self.audio = audio_track
        self.video = video_track
```

**Step 4: 修改 connectionstatechange 处理**

找到 `@pc.on("connectionstatechange")` 部分，修改清理逻辑：

```python
@pc.on("connectionstatechange")
async def on_connectionstatechange():
    logger.debug(f"[WEBRTC] Connection state changed: {pc.connectionState} for session {sessionid}")

    if pc.connectionState in ("disconnected", "failed", "closed"):
        logger.warning(f"[WEBRTC] Connection {pc.connectionState} for session {sessionid}")

        # 销毁会话进程
        await session_manager.destroy_session(sessionid)

        # Close peer connection and cleanup
        try:
            await pc.close()
            pcs.discard(pc)
            logger.debug(f"[WEBRTC] Cleaned up {pc.connectionState} session {sessionid}")
        except Exception as e:
            logger.error(f"[WEBRTC] Error cleaning up {pc.connectionState} session: {str(e)}")
```

**Step 5: 提交修改**

```bash
git add src/main/app.py
git commit -m "feat(session-isolation): modify /offer to use process isolation

- 使用 SessionManager 创建会话
- 使用 QueueAudioTrack 和 QueueVideoTrack
- 修改连接状态变化时的清理逻辑
- 添加 SimplePlayer 类
"
```

---

## Task 7: 实现 /destroy 接口

**Files:**
- Modify: `src/main/app.py`

**Step 1: 添加 destroy 接口**

```python
@app.route('/api/session/<session_id>/destroy', methods=['POST'])
async def destroy_session(request):
    """主动销毁指定会话"""

    session_id = request.match_info['session_id']

    logger.info(f"[DESTROY] Destroy request for session {session_id}")

    # 检查会话是否存在
    if not session_manager.has_session(session_id):
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": "Session not found"}),
            status=404
        )

    # 销毁会话
    success = await session_manager.destroy_session(session_id)

    if success:
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "msg": "Session destroyed"})
        )
    else:
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": "Failed to destroy session"}),
            status=500
        )
```

**Step 2: 修改 /offer 返回值添加 destroy_url**

找到 offer 函数的返回语句，添加 destroy_url：

```python
return web.Response(
    content_type="application/json",
    text=json.dumps({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "sessionid": sessionid,
        "destroy_url": f"/api/session/{sessionid}/destroy",
        "code": 0
    }),
)
```

**Step 3: 提交修改**

```bash
git add src/main/app.py
git commit -m "feat(session-isolation): add /destroy endpoint

- 实现 /api/session/<id>/destroy 接口
- 在 /offer 返回值中添加 destroy_url
- 添加会话存在性检查
"
```

---

## Task 8: 完善子进程帧传输逻辑

**Files:**
- Modify: `src/main/session_process.py`

**Step 1: 实现完整的帧传输**

替换 `_session_main` 函数中的 TODO 部分：

```python
def _session_main(session_id: str, avatar_id: str, opt: Any,
                  command_queue: multiprocessing.Queue,
                  audio_queue: multiprocessing.Queue,
                  video_queue: multiprocessing.Queue,
                  status_queue: multiprocessing.Queue):
    """子进程主函数"""
    import sys
    import os
    import time
    from threading import Event, Thread
    from queue import Queue as ThreadQueue

    try:
        import setproctitle
        setproctitle.setproctitle(f"livetalking-session-{session_id}")
    except:
        pass

    logger.info(f"[Session-{session_id}] Process started (pid={os.getpid()})")

    quit_event = Event()
    frame_queue = ThreadQueue(maxsize=100)

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from core.lipreal import LipReal

        # 初始化 LipReal
        nerfreal = build_nerfreal_subprocess(session_id, avatar_id, opt)
        nerfreal.sessionid = session_id

        logger.info(f"[Session-{session_id}] LipReal initialized")

        # 创建包装器用于捕获帧
        class FrameCapture:
            def __init__(self):
                self.audio_frames = []
                self.video_frames = []

        frame_capture = FrameCapture()

        # 修改 nerfreal 的 put 方法来捕获帧
        original_put_audio = nerfreal.put_audio_frame if hasattr(nerfreal, 'put_audio_frame') else None

        def capture_put_audio(frame, eventpoint):
            if original_put_audio:
                original_put_audio(frame, eventpoint)
            # 将音频帧放入队列
            try:
                frame_queue.put(('audio', frame, eventpoint), block=False)
            except:
                pass

        # 替换 put_audio_frame
        if hasattr(nerfreal, 'put_audio_frame'):
            nerfreal.put_audio_frame = capture_put_audio

        # 发送就绪信号
        status_queue.put({"status": "ready"})

        # 启动渲染
        render_thread = Thread(target=nerfreal.render, args=(quit_event,))
        render_thread.start()

        # 帧传输循环
        logger.info(f"[Session-{session_id}] Starting frame transfer loop")

        last_send_time = time.time()

        while not quit_event.is_set():
            # 检查控制命令
            try:
                cmd = command_queue.get(block=False)
                if cmd.get("action") == "stop":
                    logger.info(f"[Session-{session_id}] Received stop command")
                    break
            except:
                pass

            # 从帧队列获取并发送到进程间队列
            try:
                frame_type, frame, eventpoint = frame_queue.get(timeout=0.1)

                if frame_type == 'audio':
                    try:
                        audio_queue.put(frame, block=False)
                    except:
                        pass
                elif frame_type == 'video':
                    try:
                        video_queue.put(frame, block=False)
                    except:
                        pass

                last_send_time = time.time()

            except:
                # 检查超时
                if time.time() - last_send_time > 5.0:
                    # 发送心跳/空帧保持连接
                    pass

        logger.info(f"[Session-{session_id}] Frame transfer loop ended")

        # 停止渲染
        quit_event.set()
        nerfreal.stop_all_threads()
        render_thread.join(timeout=5)

    except Exception as e:
        logger.error(f"[Session-{session_id}] Error in session_main: {e}")
        import traceback
        logger.error(traceback.format_exc())
        status_queue.put({"status": "error", "message": str(e)})
    finally:
        logger.info(f"[Session-{session_id}] Cleaning up")
        quit_event.set()

        # 发送结束信号
        try:
            audio_queue.put(None, timeout=1)
            video_queue.put(None, timeout=1)
        except:
            pass

        # 关闭队列
        try:
            command_queue.close()
            audio_queue.close()
            video_queue.close()
            status_queue.close()
        except:
            pass

        logger.info(f"[Session-{session_id}] Process exiting")
```

**Step 2: 提交修改**

```bash
git add src/main/session_process.py
git commit -m "feat(session-isolation): implement complete frame transfer

- 使用 ThreadQueue 在进程内捕获帧
- 替换 nerfreal.put_audio_frame 捕获音频帧
- 实现帧传输到进程间队列
- 添加完整的清理逻辑
"
```

---

## Task 9: 前端集成 destroy 调用

**Files:**
- Modify: `frontend/web/client.js` 或相关前端文件

**Step 1: 添加 destroy 调用函数**

在前端的断开连接函数中添加：

```javascript
async function disconnect() {
    // 1. 停止本地媒体流
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
    }

    // 2. 关闭 WebRTC 连接
    if (pc) {
        pc.close();
        pc = null;
    }

    // 3. 调用 destroy 接口清理会话
    if (sessionId && destroyUrl) {
        try {
            // 使用 fetch 发送 destroy 请求
            await fetch(destroyUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({})
            });
            console.log('[Disconnect] Session destroyed successfully');
        } catch (e) {
            console.error('[Disconnect] Failed to destroy session:', e);
            // 即使 destroy 失败也继续清理
        }
        sessionId = null;
        destroyUrl = null;
    }

    // 4. 更新 UI
    updateConnectionStatus('disconnected');
}
```

**Step 2: 添加页面关闭前清理**

```javascript
// 监听页面关闭事件
window.addEventListener('beforeunload', () => {
    if (sessionId && destroyUrl) {
        // 使用 sendBeacon 确保请求发送
        navigator.sendBeacon(
            destroyUrl,
            JSON.stringify({})
        );
    }
});

// 监听页面隐藏（用户切换标签等）
document.addEventListener('visibilitychange', () => {
    if (document.hidden && sessionId && destroyUrl) {
        // 可选：自动断开连接
        // disconnect();
    }
});
```

**Step 3: 保存 destroyUrl**

在连接成功后保存 destroy_url：

```javascript
async function startCall() {
    const response = await fetch('/offer', {
        method: 'POST',
        body: JSON.stringify({
            sdp: offer.sdp,
            type: offer.type,
            avatar_id: avatarId
        })
    });

    const data = await response.json();

    if (data.code === 0) {
        sessionId = data.sessionid;
        destroyUrl = data.destroy_url;  // 保存 destroy URL

        // ... 其他连接逻辑
    }
}
```

**Step 4: 提交修改**

```bash
git add frontend/
git commit -m "feat(session-isolation): integrate destroy call in frontend

- 添加 disconnect 函数调用 destroy 接口
- 实现页面关闭前清理
- 保存 destroy_url 用于后续调用
- 添加错误处理
"
```

---

## Task 10: 添加配置开关

**Files:**
- Modify: `src/main/app.py`
- Modify: `.env` 或创建配置文件

**Step 1: 添加环境变量支持**

```python
# 在 app.py 顶部添加
USE_PROCESS_ISOLATION = os.getenv("USE_PROCESS_ISOLATION", "true").lower() == "true"
logger.info(f"[APP] Process isolation: {USE_PROCESS_ISOLATION}")
```

**Step 2: 修改 offer 函数支持开关**

```python
async def offer(request):
    # ... 前面的验证逻辑 ...

    if USE_PROCESS_ISOLATION:
        # 使用进程隔离
        session = await session_manager.create_session(sessionid, avatar_id, opt)
        if not session:
            return web.Response(...)
        audio_track = QueueAudioTrack(session.audio_queue, sessionid)
        video_track = QueueVideoTrack(session.video_queue, sessionid)
    else:
        # 使用原有逻辑（直接创建 nerfreal）
        nerfreal = await asyncio.wait_for(...)
        nerfreals[sessionid] = nerfreal
        player = HumanPlayer(nerfreal)
        audio_track = player.audio
        video_track = player.video

    # ... 后续逻辑相同 ...
```

**Step 3: 添加环境变量到 .env**

```bash
# .env
USE_PROCESS_ISOLATION=true
```

**Step 4: 提交修改**

```bash
git add src/main/app.py .env
git commit -m "feat(session-isolation): add configuration switch

- 添加 USE_PROCESS_ISOLATION 环境变量
- 支持通过配置开关选择隔离模式
- 默认启用进程隔离
"
```

---

## Task 11: 测试验证

**测试步骤：**

**Step 1: 单元测试 - 创建和销毁会话**

```python
# tests/test_session_manager.py
import pytest
import asyncio
from session_manager import SessionManager

@pytest.mark.asyncio
async def test_create_and_destroy_session():
    """测试会话创建和销毁"""
    manager = SessionManager(max_sessions=2)

    # 创建会话
    session = await manager.create_session("test001", "avatar_1", opt)
    assert session is not None
    assert session.status == SessionStatus.RUNNING

    # 销毁会话
    result = await manager.destroy_session("test001")
    assert result is True
    assert not manager.has_session("test001")

@pytest.mark.asyncio
async def test_max_sessions():
    """测试会话数量限制"""
    manager = SessionManager(max_sessions=2)

    await manager.create_session("test001", "avatar_1", opt)
    await manager.create_session("test002", "avatar_1", opt)

    # 第三个会话应该失败
    session3 = await manager.create_session("test003", "avatar_1", opt)
    assert session3 is None
```

**运行测试：**
```bash
pytest tests/test_session_manager.py -v
```

**Step 2: 集成测试 - 完整连接流程**

```bash
# 1. 启动服务
export USE_PROCESS_ISOLATION=true
python src/main/app.py --listenport 8011

# 2. 打开前端
# http://localhost:8011/dashboard.html

# 3. 测试步骤:
#    - 点击"连接"
#    - 验证音视频正常
#    - 点击"断开"
#    - 等待 5 秒
#    - 再次点击"连接"
#    - 验证连接成功
#    - 重复 10 次

# 4. 检查日志
# tail -f logs/livetalking.log | grep -E "Session|destroy"
```

**Step 3: 压力测试**

```bash
# 创建测试脚本
cat > test_session_stress.py << 'EOF'
import asyncio
import aiohttp

async def test_repeated_connect():
    async with aiohttp.ClientSession() as session:
        for i in range(100):
            # 连接
            async with session.post('http://localhost:8011/offer', json={
                'sdp': 'test_sdp',
                'type': 'offer',
                'avatar_id': 'avatar_1'
            }) as resp:
                data = await resp.json()
                session_id = data.get('sessionid')
                destroy_url = data.get('destroy_url')

            # 断开
            if destroy_url:
                async with session.post(destroy_url) as resp:
                    pass

            print(f"Cycle {i+1}/100 completed")
            await asyncio.sleep(1)

asyncio.run(test_repeated_connect())
EOF

python test_session_stress.py
```

**Step 4: 资源监控测试**

```bash
# 监控 GPU 内存
nvidia-smi -l 1

# 监控进程
watch -n 1 'ps aux | grep python | grep livetalking'

# 监控会话数
watch -n 1 'curl -s http://localhost:8011/api/sessions/count'
```

**Step 5: 提交测试文件**

```bash
git add tests/
git commit -m "test(session-isolation): add integration and stress tests

- 添加会话管理器单元测试
- 添加连接流程集成测试
- 添加压力测试脚本
- 添加资源监控指南
"
```

---

## Task 12: 文档和配置

**Files:**
- Create: `docs/session-isolation-guide.md`
- Modify: `README.md`

**Step 1: 创建使用指南**

```markdown
# 会话进程隔离使用指南

## 概述

会话进程隔离功能将每个数字人会话运行在独立的子进程中，彻底解决资源泄漏和阻塞问题。

## 启用/禁用

通过环境变量控制：

```bash
# 启用进程隔离（默认）
export USE_PROCESS_ISOLATION=true

# 禁用进程隔离（使用原有逻辑）
export USE_PROCESS_ISOLATION=false
```

## API 接口

### 销毁会话

```bash
POST /api/session/<session_id>/destroy
```

**响应：**
```json
{
  "code": 0,
  "msg": "Session destroyed"
}
```

### 查询会话状态

```bash
GET /api/session/<session_id>/status
```

**响应：**
```json
{
  "session_id": "xxx",
  "status": "running",
  "pid": 12345,
  "uptime": 120,
  "code": 0
}
```

## 前端集成

断开连接时自动调用 destroy 接口：

```javascript
async function disconnect() {
    await pc.close();
    await fetch(`/api/session/${sessionId}/destroy`, {
        method: 'POST'
    });
}
```

## 监控和调试

### 查看活动会话

```bash
tail -f logs/livetalking.log | grep "Session"
```

### 查看进程

```bash
ps aux | grep livetalking-session
```

### 查看资源使用

```bash
nvidia-smi
```

## 故障排查

### 问题：会话无法创建

**检查：**
1. 是否达到会话数量限制
2. GPU 内存是否充足
3. avatar 是否存在

### 问题：会话无法销毁

**检查：**
1. 进程是否响应
2. 是否需要强制终止

```bash
# 手动终止进程
kill -9 <pid>
```
```

**Step 2: 更新 README**

在 `README.md` 中添加：

```markdown
## 进程隔离模式

本项目支持会话进程隔离，每个数字人会话运行在独立子进程中。

### 优势

- ✅ 彻底隔离，单个会话崩溃不影响其他会话
- ✅ 强制清理，无资源泄漏风险
- ✅ 可监控进程状态，便于调试

### 配置

```bash
# .env
USE_PROCESS_ISOLATION=true
MAX_SESSIONS=10
SESSION_IDLE_TIMEOUT=300
```

### API

详见：[会话进程隔离使用指南](docs/session-isolation-guide.md)
```

**Step 3: 提交文档**

```bash
git add docs/ README.md
git commit -m "docs(session-isolation): add user guide and documentation

- 添加会话进程隔离使用指南
- 更新 README 添加进程隔离说明
- 添加 API 接口文档
- 添加故障排查指南
"
```

---

## Task 13: 代码审查和优化

**审查清单：**

**Step 1: 检查资源泄漏**

```bash
# 运行内存分析
python -m memory_profiler src/main/app.py

# 检查进程数
ps aux | grep python | wc -l

# 检查 GPU 内存
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

**Step 2: 检查性能影响**

```bash
# 基准测试
ab -n 1000 -c 10 http://localhost:8011/api/status

# 延迟测试
curl -w "@curl-format.txt" http://localhost:8011/offer
```

**Step 3: 安全审查**

检查点：
- [ ] session_id 注入防护
- [ ] 进程权限控制
- [ ] 队列大小限制
- [ ] 超时保护

**Step 4: 提交优化**

```bash
git add .
git commit -m "refactor(session-isolation): code review optimizations

- 添加资源泄漏检查
- 优化性能热点
- 加强安全防护
- 添加更多日志
"
```

---

## Task 14: 最终测试和发布

**Step 1: 完整回归测试**

```bash
# 1. 功能测试
pytest tests/ -v

# 2. 集成测试
python scripts/integration_test.py

# 3. 压力测试
python scripts/stress_test.py

# 4. 长时间稳定性测试（24小时）
nohup python scripts/stability_test.py > stability.log 2>&1 &
```

**Step 2: 创建发布标签**

```bash
git tag -a v2.0.0-session-isolation -m "会话进程隔离功能发布

- 实现会话进程隔离
- 添加 /destroy 接口
- 前端集成自动清理
- 添加配置开关
"
git push origin feature/session-process-isolation
git push origin v2.0.0-session-isolation
```

**Step 3: 创建 Pull Request**

```bash
gh pr create --title "feat: 会话进程隔离功能" --body "
## 功能说明

实现会话进程隔离，彻底解决资源泄漏和阻塞问题。

## 主要变更

- 添加 SessionProcess 类封装子进程
- 添加 SessionManager 管理会话生命周期
- 添加 QueueMediaTrack 用于进程间通信
- 实现 /destroy 接口
- 前端集成自动清理

## 测试

- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 压力测试通过
- [ ] 24小时稳定性测试通过

## 文档

- [ ] 使用指南已更新
- [ ] README 已更新
- [ ] API 文档已更新
"
```

**Step 4: 合并到主分支**

```bash
git checkout main
git merge feature/session-process-isolation
git push origin main
```

---

## 风险点和应对措施

### 风险 1: 进程间通信性能

**描述**: multiprocessing.Queue 序列化可能影响性能

**应对**:
- 使用共享内存优化（可选）
- 设置合理的队列大小
- 监控传输延迟

### 风险 2: GPU 内存占用

**描述**: 每个进程独立占用 GPU 内存

**应对**:
- 设置会话数量限制
- 监控 GPU 内存使用
- 必要时使用模型共享

### 风险 3: 进程无法终止

**描述**: 子进程可能无法响应终止信号

**应对**:
- 多级终止策略（stop → terminate → kill）
- 设置超时保护
- 强制清理机制

### 风险 4: 兼容性问题

**描述**: 新旧模式切换可能有问题

**应对**:
- 保留配置开关
- 充分测试两种模式
- 提供回滚方案

---

## 实施时间估算

| 任务 | 预计时间 |
|------|---------|
| Task 1-2: 创建核心类 | 2-3 小时 |
| Task 3-5: 实现帧传输 | 3-4 小时 |
| Task 6-7: 集成到主应用 | 2-3 小时 |
| Task 8: 完善子进程逻辑 | 2-3 小时 |
| Task 9: 前端集成 | 1-2 小时 |
| Task 10: 配置开关 | 1 小时 |
| Task 11: 测试验证 | 3-4 小时 |
| Task 12-14: 文档发布 | 2-3 小时 |
| **总计** | **16-23 小时** |

---

## 下一步

Plan complete and saved to `docs/plans/2026-03-14-session-isolation-implementation.md`.

Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
