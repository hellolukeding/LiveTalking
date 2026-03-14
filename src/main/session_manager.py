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
