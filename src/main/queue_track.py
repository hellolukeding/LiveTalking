# src/main/queue_track.py
"""从 multiprocessing.Queue 读取的 WebRTC 媒体轨道 - 支持序列化数据"""

import asyncio
import logging
import numpy as np
from av import AudioFrame, VideoFrame
from aiortc import MediaStreamTrack
from typing import Optional
import multiprocessing

logger = logging.getLogger(__name__)


class QueueAudioTrack(MediaStreamTrack):
    """从队列读取音频的 WebRTC 轨道 - 支持序列化数据"""

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
            # 从队列获取音频帧数据（带超时）
            frame_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.queue.get(timeout=1.0)
            )

            if frame_data is None:  # 结束信号
                logger.info(f"[QueueAudioTrack] Session {self.session_id} received end signal")
                self._stopped = True
                raise StopIteration

            # 如果是字典（序列化数据），重建 AudioFrame
            if isinstance(frame_data, dict):
                audio_frame = AudioFrame(
                    format=frame_data['format'],
                    layout=frame_data['layout'],
                    samples=frame_data['samples']
                )
                # 恢复 plane 数据
                for i, plane_bytes in enumerate(frame_data['planes']):
                    audio_frame.planes[i].update(plane_bytes)

                self._timestamp += audio_frame.samples
                audio_frame.pts = self._timestamp
                audio_frame.time_base = "1/48000"  # 48kHz
                return audio_frame
            else:
                # 直接是 AudioFrame 对象
                if isinstance(frame_data, AudioFrame):
                    self._timestamp += frame_data.samples
                    frame_data.pts = self._timestamp
                    frame_data.time_base = "1/48000"
                    return frame_data
                else:
                    # numpy 数组
                    audio_frame = AudioFrame.from_ndarray(frame_data, format='s16', layout='mono')
                    self._timestamp += audio_frame.samples
                    audio_frame.pts = self._timestamp
                    audio_frame.time_base = "1/48000"
                    return audio_frame

        except Exception as e:
            logger.error(f"[QueueAudioTrack] Error receiving frame: {e}")
            # 返回静音帧避免卡顿
            return AudioFrame(format='s16', layout='mono', samples=960)


class QueueVideoTrack(MediaStreamTrack):
    """从队列读取视频的 WebRTC 轨道 - 支持序列化数据"""

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
            # 从队列获取视频帧数据（带超时）
            frame_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.queue.get(timeout=1.0)
            )

            if frame_data is None:  # 结束信号
                logger.info(f"[QueueVideoTrack] Session {self.session_id} received end signal")
                self._stopped = True
                raise StopIteration

            # 如果是字典（序列化数据），重建 VideoFrame
            if isinstance(frame_data, dict):
                video_frame = VideoFrame(
                    width=frame_data['width'],
                    height=frame_data['height']
                )
                # 恢复数据
                if 'data' in frame_data:
                    video_frame.update(frame_data['data'])

                self._timestamp += 1
                video_frame.pts = self._timestamp
                video_frame.time_base = "1/90000"  # 90kHz (RTP 标准)
                return video_frame
            else:
                # 直接是 VideoFrame 对象
                if isinstance(frame_data, VideoFrame):
                    self._timestamp += 1
                    frame_data.pts = self._timestamp
                    frame_data.time_base = "1/90000"
                    return frame_data
                else:
                    # numpy 数组
                    import numpy as np
                    video_frame = VideoFrame.from_ndarray(frame_data, format='bgr24')
                    self._timestamp += 1
                    video_frame.pts = self._timestamp
                    video_frame.time_base = "1/90000"
                    return video_frame

        except Exception as e:
            logger.error(f"[QueueVideoTrack] Error receiving frame: {e}")
            # 超时或错误时抛出 StopIteration
            raise StopIteration
