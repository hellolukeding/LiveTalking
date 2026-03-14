# src/main/queue_track.py
"""从 multiprocessing.Queue 读取的 WebRTC 媒体轨道 - 支持序列化数据"""

import asyncio
import logging
import numpy as np
from av import AudioFrame, VideoFrame
from aiortc import MediaStreamTrack
from typing import Optional
import multiprocessing

from frame_serializer import deserialize_audio_frame, deserialize_video_frame

logger = logging.getLogger(__name__)


class QueueAudioTrack(MediaStreamTrack):
    """从队列读取音频的 WebRTC 轨道 - 支持序列化数据"""
    kind = "audio"

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
            # 从队列获取序列化的帧数据
            frame_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.queue.get(timeout=1.0)
            )

            if frame_data is None:
                logger.info(f"[QueueAudioTrack] Session {self.session_id} received end signal")
                self._stopped = True
                raise StopIteration

            # 使用 frame_serializer 反序列化
            audio_frame = deserialize_audio_frame(frame_data)

            self._timestamp += audio_frame.samples
            audio_frame.pts = self._timestamp
            audio_frame.time_base = "1/48000"
            return audio_frame

        except Exception as e:
            logger.error(f"[QueueAudioTrack] Error receiving frame: {e}")
            return AudioFrame(format='s16', layout='mono', samples=960)


class QueueVideoTrack(MediaStreamTrack):
    """从队列读取视频的 WebRTC 轨道 - 支持序列化数据"""
    kind = "video"

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
            # 从队列获取序列化的帧数据
            frame_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.queue.get(timeout=1.0)
            )

            if frame_data is None:
                logger.info(f"[QueueVideoTrack] Session {self.session_id} received end signal")
                self._stopped = True
                raise StopIteration

            # 使用 frame_serializer 反序列化
            video_frame = deserialize_video_frame(frame_data)

            self._timestamp += 1
            video_frame.pts = self._timestamp
            video_frame.time_base = "1/90000"
            return video_frame

        except Exception as e:
            logger.error(f"[QueueVideoTrack] Error receiving frame: {e}")
            raise StopIteration
