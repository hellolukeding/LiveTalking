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

# 为子进程添加文件日志
import os
if os.getpid() != os.getppid():  # 如果是子进程
    log_file = f"/tmp/session_{os.getpid()}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().setLevel(logging.DEBUG)


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
    子进程主函数 - 完整版本，实现音视频帧传输
    """
    import sys
    import os
    import time
    import numpy as np
    from threading import Event, Thread
    from queue import Queue as ThreadQueue
    from av import AudioFrame, VideoFrame

    # 设置进程名称
    try:
        import setproctitle
        setproctitle.setproctitle(f"livetalking-session-{session_id}")
    except:
        pass

    logger.info(f"[Session-{session_id}] Process started (pid={os.getpid()})")

    quit_event = Event()
    audio_frame_queue = ThreadQueue(maxsize=100)
    video_frame_queue = ThreadQueue(maxsize=100)

    try:
        # 导入必要的模块（在子进程中）
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from core.lipreal import LipReal
        from aiortc import MediaStreamTrack

        # 初始化 LipReal
        nerfreal = build_nerfreal_subprocess(session_id, avatar_id, opt)
        nerfreal.sessionid = session_id

        logger.info(f"[Session-{session_id}] LipReal initialized")

        # 创建假的音视频轨道，用于捕获输出
        # 使用简化的 Queue 对象，其 put() 方法是一个真正的 async coroutine
        class SimpleQueue:
            """简单的异步队列，put() 方法返回真正的 coroutine"""
            def __init__(self, thread_queue, name="Queue"):
                self.thread_queue = thread_queue
                self.name = name
                self.count = 0

            async def put(self, item):
                """异步 put 方法 - 返回真正的 coroutine"""
                try:
                    self.thread_queue.put_nowait(item)
                    self.count += 1
                    if self.count % 50 == 0:
                        logger.info(f"[Session-{session_id}] {self.name}: Put {self.count} items")
                except Exception as e:
                    logger.error(f"[Session-{session_id}] {self.name}.put() error: {e}")
                # 必须 await 才能让 run_coroutine_threadsafe 正常工作
                await asyncio.sleep(0)

        class FakeAudioTrack(MediaStreamTrack):
            kind = "audio"

            def __init__(self, queue_ref):
                super().__init__()
                self.queue_ref = queue_ref  # ThreadQueue
                # 创建一个独立的 queue 对象，其 put() 是真正的 async 方法
                self._queue_obj = SimpleQueue(queue_ref, "AudioQueue")
                self._stopped = False

            @property
            def _queue(self):
                # 返回独立的 queue 对象，而不是 self
                return self._queue_obj

            async def recv(self):
                if self._stopped:
                    raise StopIteration
                try:
                    frame = self.queue_ref.get(timeout=0.1)
                    if frame is None:
                        self._stopped = True
                        raise StopIteration
                    return frame
                except:
                    # 返回静音帧
                    return AudioFrame(format='s16', layout='mono', samples=960)

        class FakeVideoTrack(MediaStreamTrack):
            kind = "video"

            def __init__(self, queue_ref):
                super().__init__()
                self.queue_ref = queue_ref  # ThreadQueue
                # 创建一个独立的 queue 对象，其 put() 是真正的 async 方法
                self._queue_obj = SimpleQueue(queue_ref, "VideoQueue")
                self._stopped = False

            @property
            def _queue(self):
                # 返回独立的 queue 对象，而不是 self
                return self._queue_obj

            async def recv(self):
                if self._stopped:
                    raise StopIteration
                try:
                    frame = self.queue_ref.get(timeout=0.1)
                    if frame is None:
                        self._stopped = True
                        raise StopIteration
                    return frame
                except:
                    raise StopIteration

        fake_audio = FakeAudioTrack(audio_frame_queue)
        fake_video = FakeVideoTrack(video_frame_queue)

        # 启动 LipReal 渲染（使用假的轨道）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        logger.info(f"[Session-{session_id}] Starting render")
        
        # 发送就绪信号
        status_queue.put({"status": "ready"})

        # 启动渲染线程
        render_thread = Thread(target=nerfreal.render, args=(quit_event, loop, fake_audio, fake_video))
        render_thread.daemon = True
        render_thread.start()

        logger.info(f"[Session-{session_id}] Render thread started")

        # 帧转发线程 - 从内部队列获取帧并发送到进程间队列
        def frame_forwarder():
            last_audio_time = time.time()
            last_video_time = time.time()
            audio_forwarded = 0
            video_forwarded = 0

            while not quit_event.is_set():
                try:
                    # 转发音频帧 - basereal.py puts (AudioFrame, eventpoint) tuples
                    try:
                        audio_tuple = audio_frame_queue.get(timeout=0.05)
                        if audio_tuple is not None:
                            # 解包元组: (AudioFrame, eventpoint)
                            audio_frame, eventpoint = audio_tuple if isinstance(audio_tuple, tuple) else (audio_tuple, None)
                            if audio_frame is not None:
                                try:
                                    # 将 AudioFrame 转换为可序列化的字典
                                    audio_bytes = {
                                        'format': audio_frame.format.name,
                                        'layout': audio_frame.layout.name,
                                        'samples': audio_frame.samples,
                                        'planes': [plane.to_bytes() for plane in audio_frame.planes]
                                    }
                                    audio_queue.put(audio_bytes, block=False)
                                    last_audio_time = time.time()
                                    audio_forwarded += 1
                                    if audio_forwarded % 100 == 0:
                                        logger.info(f"[Session-{session_id}] Forwarded {audio_forwarded} audio frames")
                                except Exception as e:
                                    logger.debug(f"[Session-{session_id}] Audio frame error: {e}")
                    except:
                        pass

                    # 转发视频帧 - basereal.py puts (VideoFrame, eventpoint) tuples
                    try:
                        video_tuple = video_frame_queue.get(timeout=0.05)
                        if video_tuple is not None:
                            # 解包元组: (VideoFrame, eventpoint)
                            video_frame, eventpoint = video_tuple if isinstance(video_tuple, tuple) else (video_tuple, None)
                            if video_frame is not None:
                                try:
                                    # 将 VideoFrame 转换为可序列化的字典
                                    height, width = video_frame.height, video_frame.width
                                    video_bytes = {
                                        'format': video_frame.format.name,
                                        'width': width,
                                        'height': height,
                                        'data': video_frame.to_bytes()
                                    }
                                    video_queue.put(video_bytes, block=False)
                                    last_video_time = time.time()
                                    video_forwarded += 1
                                    if video_forwarded % 50 == 0:
                                        logger.info(f"[Session-{session_id}] Forwarded {video_forwarded} video frames")
                                except Exception as e:
                                    logger.debug(f"[Session-{session_id}] Video frame error: {e}")
                    except:
                        pass

                    # 检查停止命令
                    try:
                        cmd = command_queue.get(block=False)
                        if cmd.get("action") == "stop":
                            logger.info(f"[Session-{session_id}] Received stop command")
                            quit_event.set()
                            break
                    except:
                        pass

                    # 检查超时
                    if time.time() - last_audio_time > 5.0:
                        # 发送心跳音频帧保持连接
                        pass

                    time.sleep(0.01)  # 避免CPU占用过高

                except Exception as e:
                    logger.error(f"[Session-{session_id}] Frame forwarder error: {e}")
                    time.sleep(0.01)

        forwarder_thread = Thread(target=frame_forwarder, daemon=True)
        forwarder_thread.start()

        logger.info(f"[Session-{session_id}] Frame forwarder started")

        # 等待渲染线程完成
        render_thread.join()
        logger.info(f"[Session-{session_id}] Render thread ended")

    except Exception as e:
        logger.error(f"[Session-{session_id}] Error in session_main: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            status_queue.put({"status": "error", "message": str(e)})
        except:
            pass
    finally:
        logger.info(f"[Session-{session_id}] Cleaning up")
        quit_event.set()

        # 停止所有线程
        if 'nerfreal' in locals():
            try:
                nerfreal.stop_all_threads()
            except:
                pass

        # 发送结束信号
        try:
            audio_queue.put(None, timeout=1)
            video_queue.put(None, timeout=1)
        except:
            pass

        # 关闭队列
        for q in [command_queue, audio_queue, video_queue, status_queue]:
            try:
                q.close()
            except:
                pass

        logger.info(f"[Session-{session_id}] Process exiting")




def build_nerfreal_subprocess(session_id: str, avatar_id: str, opt: Any):
    """在子进程中构建 LipReal 实例"""
    # 添加 sessionid 到 opt
    opt.sessionid = session_id
    from core.lipreal import LipReal, load_model, load_avatar

    # 加载模型（全局单例，只加载一次）
    if not hasattr(build_nerfreal_subprocess, '_model'):
        model_path = "./models/wav2lip384.pth"
        build_nerfreal_subprocess._model = load_model(model_path)
        logger.info(f"[Session-{session_id}] Model loaded")

    model = build_nerfreal_subprocess._model

    # 加载 avatar (load_avatar 返回 4 个值，只传前 3 个给 LipReal)
    frame_list, face_list, coord_list, _ = load_avatar(avatar_id)
    logger.info(f"[Session-{session_id}] Avatar loaded: {avatar_id}")

    # 创建 LipReal 实例
    nerfreal = LipReal(opt, model, (frame_list, face_list, coord_list))

    return nerfreal
