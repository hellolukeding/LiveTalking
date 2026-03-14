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
