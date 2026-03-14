# src/main/queue_track.py
"""从 multiprocessing.Queue 读取的 WebRTC 媒体轨道"""

import asyncio
import logging
import numpy as np
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
                video_frame = VideoFrame.from_ndarray(frame, format='bgr24')
                self._timestamp += 1
                video_frame.pts = self._timestamp
                video_frame.time_base = "1/90000"
                return video_frame

        except Exception as e:
            logger.error(f"[QueueVideoTrack] Error receiving frame: {e}")
            raise StopIteration
