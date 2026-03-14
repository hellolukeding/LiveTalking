# src/main/queue_track.py
"""从 multiprocessing.Queue 读取的 WebRTC 媒体轨道 - 支持序列化数据"""

import asyncio
import logging
import fractions
import numpy as np
from av import AudioFrame, VideoFrame
from aiortc import MediaStreamTrack
from typing import Optional
import multiprocessing
import queue as std_queue

from frame_serializer import deserialize_audio_frame, deserialize_video_frame

logger = logging.getLogger(__name__)

VIDEO_CLOCK_RATE = 90000
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)
DEFAULT_VIDEO_FPS = 25
DEFAULT_VIDEO_PTS_STEP = int(VIDEO_CLOCK_RATE / DEFAULT_VIDEO_FPS)  # 3600 @ 25fps

DEFAULT_AUDIO_SAMPLE_RATE = 16000
DEFAULT_AUDIO_SAMPLES = int(DEFAULT_AUDIO_SAMPLE_RATE * 0.020)  # 20ms -> 320


class QueueAudioTrack(MediaStreamTrack):
    """从队列读取音频的 WebRTC 轨道 - 支持序列化数据"""
    kind = "audio"

    def __init__(self, queue: multiprocessing.Queue, session_id: str):
        super().__init__()
        self.queue = queue
        self.session_id = session_id
        self._timestamp = 0  # in samples
        self._stopped = False

        logger.info(f"[QueueAudioTrack] Created for session {session_id}")

    async def recv(self):
        """接收下一帧"""
        if self._stopped:
            raise StopIteration

        while True:
            try:
                frame_data = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.queue.get(timeout=0.5)
                )
            except std_queue.Empty:
                continue

            if frame_data is None:
                logger.info(f"[QueueAudioTrack] Session {self.session_id} received end signal")
                self._stopped = True
                raise StopIteration

            try:
                audio_frame = deserialize_audio_frame(frame_data)
            except Exception as e:
                logger.error(f"[QueueAudioTrack] Failed to deserialize audio frame: {e}")
                silence = np.zeros((1, DEFAULT_AUDIO_SAMPLES), dtype=np.int16)
                audio_frame = AudioFrame.from_ndarray(silence, layout="mono", format="s16")

            # Ensure sample rate / timestamps
            sample_rate = getattr(audio_frame, "sample_rate", None) or frame_data.get("sample_rate") or DEFAULT_AUDIO_SAMPLE_RATE
            try:
                audio_frame.sample_rate = sample_rate
            except Exception:
                pass

            audio_frame.pts = self._timestamp
            audio_frame.time_base = fractions.Fraction(1, int(sample_rate))
            self._timestamp += int(audio_frame.samples)
            return audio_frame


class QueueVideoTrack(MediaStreamTrack):
    """从队列读取视频的 WebRTC 轨道 - 支持序列化数据"""
    kind = "video"

    def __init__(self, queue: multiprocessing.Queue, session_id: str):
        super().__init__()
        self.queue = queue
        self.session_id = session_id
        self._timestamp = 0  # in 90kHz clock units
        self._stopped = False
        self._pts_step = DEFAULT_VIDEO_PTS_STEP

        logger.info(f"[QueueVideoTrack] Created for session {session_id}")

    async def recv(self):
        """接收下一帧"""
        if self._stopped:
            raise StopIteration

        while True:
            try:
                frame_data = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.queue.get(timeout=0.5)
                )
            except std_queue.Empty:
                continue

            if frame_data is None:
                logger.info(f"[QueueVideoTrack] Session {self.session_id} received end signal")
                self._stopped = True
                raise StopIteration

            try:
                video_frame = deserialize_video_frame(frame_data)
            except Exception as e:
                logger.error(f"[QueueVideoTrack] Failed to deserialize video frame: {e}")
                # Keep waiting rather than terminating the whole track.
                continue

            video_frame.pts = self._timestamp
            video_frame.time_base = VIDEO_TIME_BASE
            self._timestamp += self._pts_step
            return video_frame
