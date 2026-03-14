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

        # 共享状态（用于主进程查询）
        self.speaking_value: Optional[multiprocessing.Value] = None

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
            self.speaking_value = multiprocessing.Value('b', False)

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
                    self.status_queue,
                    self.speaking_value,
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
                  status_queue: multiprocessing.Queue,
                  speaking_value: multiprocessing.Value):
    """
    子进程主函数 - 完整版本，实现音视频帧传输
    """
    import sys
    import os
    import time
    import numpy as np
    from threading import Event, Thread
    from av import AudioFrame, VideoFrame

    # 设置进程名称
    try:
        import setproctitle
        setproctitle.setproctitle(f"livetalking-session-{session_id}")
    except:
        pass

    logger.info(f"[Session-{session_id}] Process started (pid={os.getpid()})")

    quit_event = Event()

    try:
        # 确保子进程 sys.path 完整（避免依赖父进程启动方式）
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        src_root = os.path.join(project_root, "src")
        for p in [
            project_root,
            src_root,
            os.path.join(src_root, "core"),
            os.path.join(src_root, "llm"),
            os.path.join(src_root, "utils"),
            os.path.join(src_root, "main"),
        ]:
            if p not in sys.path:
                sys.path.insert(0, p)

        # 导入必要的模块（在子进程中）
        from core.lipreal import LipReal

        # 初始化 LipReal
        nerfreal = build_nerfreal_subprocess(session_id, avatar_id, opt)
        nerfreal.sessionid = session_id

        # 创建直接队列写入器 - basereal.py 调用 _queue.put() 时直接序列化并写入 mp.Queue
        from frame_serializer import serialize_audio_frame, serialize_video_frame

        class DirectFrameWriter:
            """直接帧写入器 - 将帧序列化并写入 multiprocessing.Queue"""
            def __init__(self, mp_queue, frame_type):
                self.mp_queue = mp_queue
                self.frame_type = frame_type
                self.count = 0

            async def put(self, frame_data):
                """异步写入方法 - basereal.py 通过 run_coroutine_threadsafe 调用"""
                try:
                    # frame_data 是 (frame, eventpoint) 元组
                    frame, eventpoint = frame_data if isinstance(frame_data, tuple) else (frame_data, None)

                    if frame is None:
                        return

                    # 序列化帧
                    if self.frame_type == 'audio':
                        serialized = serialize_audio_frame(frame)
                    else:
                        serialized = serialize_video_frame(frame)

                    # 写入 multiprocessing.Queue
                    self.mp_queue.put(serialized, block=False)

                    self.count += 1
                    if self.count % 50 == 0:
                        logger.info(f"[Session-{session_id}] {self.frame_type}: Put {self.count} frames")

                except Exception as e:
                    logger.error(f"[Session-{session_id}] {self.frame_type}.put() error: {e}")
                # 立即返回，不等待
                return

        class FakeAudioTrack:
            """假的音频轨道 - _queue 是 DirectFrameWriter"""
            kind = "audio"

            def __init__(self, mp_queue):
                self._queue = DirectFrameWriter(mp_queue, 'audio')

            async def recv(self):
                raise StopIteration  # 这个方法不会被调用

        class FakeVideoTrack:
            """假的视频轨道 - _queue 是 DirectFrameWriter"""
            kind = "video"

            def __init__(self, mp_queue):
                self._queue = DirectFrameWriter(mp_queue, 'video')

            async def recv(self):
                raise StopIteration  # 这个方法不会被调用

        logger.info(f"[Session-{session_id}] LipReal initialized")

        # 不再需要 ThreadQueue 和 frame_forwarder
        # 直接创建 FakeTrack，传递 multiprocessing.Queue
        fake_audio = FakeAudioTrack(audio_queue)
        fake_video = FakeVideoTrack(video_queue)

        logger.info(f"[Session-{session_id}] Using direct frame writers")

        # 命令处理线程：主进程通过 command_queue 控制说话/打断/停止
        def command_loop():
            logger.info(f"[Session-{session_id}] Command loop started")
            while not quit_event.is_set():
                try:
                    cmd = command_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"[Session-{session_id}] Command queue error: {e}")
                    continue

                if cmd is None:
                    continue
                if not isinstance(cmd, dict):
                    logger.warning(f"[Session-{session_id}] Invalid command type: {type(cmd)}")
                    continue

                action = cmd.get("action")
                try:
                    if action == "stop":
                        logger.info(f"[Session-{session_id}] Received stop command")
                        quit_event.set()
                        break
                    elif action == "interrupt":
                        if hasattr(nerfreal, "flush_talk"):
                            nerfreal.flush_talk()
                            logger.info(f"[Session-{session_id}] Interrupted talk")
                    elif action == "say":
                        text = (cmd.get("text") or "").strip()
                        if not text:
                            continue
                        datainfo = cmd.get("datainfo") or {}
                        if hasattr(nerfreal, "put_msg_txt"):
                            nerfreal.put_msg_txt(text, datainfo)
                            logger.info(f"[Session-{session_id}] Queued text: {text[:30]}...")
                    else:
                        logger.warning(f"[Session-{session_id}] Unknown action: {action}")
                except Exception as e:
                    logger.error(f"[Session-{session_id}] Command handling error: {e}")

            logger.info(f"[Session-{session_id}] Command loop stopped")

        command_thread = Thread(target=command_loop, daemon=True)
        command_thread.start()

        # 说话状态同步线程（供主进程 is_speaking 查询）
        def speaking_monitor():
            while not quit_event.is_set():
                try:
                    speaking_value.value = bool(getattr(nerfreal, "speaking", False))
                except Exception:
                    pass
                time.sleep(0.2)

        speaking_thread = Thread(target=speaking_monitor, daemon=True)
        speaking_thread.start()

        # 启动 LipReal 渲染（使用假的轨道）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        logger.info(f"[Session-{session_id}] Starting render")
        
        # 发送就绪信号
        status_queue.put({"status": "ready"})

        # 启动事件循环线程 - run_coroutine_threadsafe 需要 loop 正在运行
        def run_event_loop():
            asyncio.set_event_loop(loop)
            loop.run_forever()
        
        loop_thread = Thread(target=run_event_loop, daemon=True)
        loop_thread.start()
        logger.info(f"[Session-{session_id}] Event loop thread started")

        # 启动渲染线程
        render_thread = Thread(target=nerfreal.render, args=(quit_event, loop, fake_audio, fake_video))
        render_thread.daemon = True
        render_thread.start()

        logger.info(f"[Session-{session_id}] Render thread started")


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

        # 停止事件循环
        if 'loop' in locals() and loop.is_running():
            try:
                loop.call_soon_threadsafe(loop.stop)
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
    import json
    from pathlib import Path

    # 加载模型（全局单例，只加载一次）
    if not hasattr(build_nerfreal_subprocess, '_model'):
        model_path = "./models/wav2lip384.pth"
        build_nerfreal_subprocess._model = load_model(model_path)
        logger.info(f"[Session-{session_id}] Model loaded")

    model = build_nerfreal_subprocess._model

    # 读取 avatar meta.json（设置 avatar_name / voice_id）
    avatar_name = avatar_id
    try:
        meta_path = Path("./data/avatars") / avatar_id / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            avatar_name = meta.get("name", avatar_name)
            voice_id = meta.get("voice_id")
            if voice_id:
                opt.REF_FILE = voice_id
    except Exception as e:
        logger.warning(f"[Session-{session_id}] Failed to load avatar meta.json: {e}")

    # 加载 avatar (load_avatar 返回 4 个值，只传前 3 个给 LipReal)
    frame_list, face_list, coord_list, _ = load_avatar(avatar_id)
    logger.info(f"[Session-{session_id}] Avatar loaded: {avatar_id}")

    # 创建 LipReal 实例
    nerfreal = LipReal(opt, model, (frame_list, face_list, coord_list), avatar_name)

    return nerfreal
