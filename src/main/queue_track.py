# src/main/queue_track.py
"""从 multiprocessing.Queue 读取的 WebRTC 媒体轨道 - 支持序列化数据"""

import asyncio
import logging
import fractions
import time
import os
import numpy as np
from av import AudioFrame, VideoFrame
from aiortc import MediaStreamTrack
from typing import Optional, Set
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
DEFAULT_AUDIO_JITTER_WAIT_S = float(os.getenv("AUDIO_JITTER_WAIT_MS", "10")) / 1000.0
DEFAULT_VIDEO_JITTER_WAIT_S = float(os.getenv("VIDEO_JITTER_WAIT_MS", "20")) / 1000.0


class AVSyncClock:
    """
    Shared A/V clock for a single WebRTC session.

    Goals:
    - Ensure audio/video start at the same wall-clock moment (avoid initial offset).
    - Provide a monotonic base time (perf_counter) for pacing.
    """

    def __init__(self, required_kinds: Optional[Set[str]] = None):
        self._required_kinds = required_kinds or {"audio", "video"}
        self._ready_kinds: Set[str] = set()
        self._start_time: Optional[float] = None
        self._ready_event: Optional[asyncio.Event] = None
        self._lock: Optional[asyncio.Lock] = None

    def _ensure_async(self):
        if self._ready_event is None:
            self._ready_event = asyncio.Event()
        if self._lock is None:
            self._lock = asyncio.Lock()

    async def mark_ready_and_wait(self, kind: str) -> float:
        self._ensure_async()
        assert self._lock is not None
        assert self._ready_event is not None

        async with self._lock:
            self._ready_kinds.add(kind)
            if self._start_time is None and self._required_kinds.issubset(self._ready_kinds):
                self._start_time = time.perf_counter()
                self._ready_event.set()

        if self._start_time is None:
            await self._ready_event.wait()
        assert self._start_time is not None
        return self._start_time


class QueueAudioTrack(MediaStreamTrack):
    """从队列读取音频的 WebRTC 轨道 - 支持序列化数据"""
    kind = "audio"

    def __init__(self, queue: multiprocessing.Queue, session_id: str, clock: Optional[AVSyncClock] = None):
        super().__init__()
        self.queue = queue
        self.session_id = session_id
        self.clock = clock or AVSyncClock()
        self._timestamp = 0  # in samples
        self._start_time: Optional[float] = None
        self._stopped = False

        logger.info(f"[QueueAudioTrack] Created for session {session_id}")

    async def recv(self):
        """接收下一帧"""
        if self._stopped:
            raise StopIteration

        # Align A/V start: do not dequeue frames until BOTH tracks have started.
        if self._start_time is None:
            self._start_time = await self.clock.mark_ready_and_wait(self.kind)
            self._timestamp = 0

        # Pace to the wall clock based on the RTP timestamp we are about to emit.
        # NOTE: aiortc sends as fast as recv() returns; pacing here prevents burst-send then starvation.
        sample_rate_hint = DEFAULT_AUDIO_SAMPLE_RATE
        target_time = self._start_time + (self._timestamp / sample_rate_hint)
        now = time.perf_counter()
        wait = target_time - now
        if wait > 0:
            await asyncio.sleep(wait)

        # Prefer non-blocking dequeue; if producer stalls, synthesize silence to keep the audio clock continuous.
        try:
            frame_data = self.queue.get_nowait()
            got_item = True
        except std_queue.Empty:
            # Small jitter wait: if producer is slightly late, wait a bit instead of injecting silence.
            try:
                frame_data = await asyncio.to_thread(self.queue.get, True, DEFAULT_AUDIO_JITTER_WAIT_S)
                got_item = True
            except std_queue.Empty:
                frame_data = None
                got_item = False

        if got_item and frame_data is None:
            logger.info(f"[QueueAudioTrack] Session {self.session_id} received end signal")
            self._stopped = True
            raise StopIteration

        if not got_item:
            # Fallback: if the producer is stalled, output silence to keep the track alive.
            silence = np.zeros((1, DEFAULT_AUDIO_SAMPLES), dtype=np.int16)
            audio_frame = AudioFrame.from_ndarray(silence, layout="mono", format="s16")
            audio_frame.sample_rate = DEFAULT_AUDIO_SAMPLE_RATE
        else:
            try:
                audio_frame = deserialize_audio_frame(frame_data)
            except Exception as e:
                logger.error(f"[QueueAudioTrack] Failed to deserialize audio frame: {e}")
                sample_rate = None
                try:
                    sample_rate = frame_data.get("sample_rate")
                except Exception:
                    sample_rate = None
                sample_rate = int(sample_rate or DEFAULT_AUDIO_SAMPLE_RATE)
                silence = np.zeros((1, DEFAULT_AUDIO_SAMPLES), dtype=np.int16)
                audio_frame = AudioFrame.from_ndarray(silence, layout="mono", format="s16")
                audio_frame.sample_rate = sample_rate

        sample_rate = int(getattr(audio_frame, "sample_rate", None) or DEFAULT_AUDIO_SAMPLE_RATE)

        audio_frame.pts = self._timestamp
        audio_frame.time_base = fractions.Fraction(1, sample_rate)
        self._timestamp += int(audio_frame.samples)
        return audio_frame


class QueueVideoTrack(MediaStreamTrack):
    """从队列读取视频的 WebRTC 轨道 - 支持序列化数据"""
    kind = "video"

    def __init__(self, queue: multiprocessing.Queue, session_id: str, clock: Optional[AVSyncClock] = None):
        super().__init__()
        self.queue = queue
        self.session_id = session_id
        self.clock = clock or AVSyncClock()
        self._timestamp = 0  # in 90kHz clock units
        self._start_time: Optional[float] = None
        self._stopped = False
        self._pts_step = DEFAULT_VIDEO_PTS_STEP
        self._last_frame: Optional[VideoFrame] = None

        logger.info(f"[QueueVideoTrack] Created for session {session_id}")

    async def recv(self):
        """接收下一帧"""
        if self._stopped:
            raise StopIteration

        # Align A/V start: do not dequeue frames until BOTH tracks have started.
        if self._start_time is None:
            self._start_time = await self.clock.mark_ready_and_wait(self.kind)
            self._timestamp = 0

        # Pace to wall clock.
        target_time = self._start_time + (self._timestamp / VIDEO_CLOCK_RATE)
        now = time.perf_counter()
        wait = target_time - now
        if wait > 0:
            await asyncio.sleep(wait)

        # Prefer non-blocking dequeue; if producer stalls, repeat last frame (keeps video clock continuous).
        try:
            frame_data = self.queue.get_nowait()
            got_item = True
        except std_queue.Empty:
            # Small jitter wait: let slightly-late frames catch up to avoid visible stutter.
            try:
                frame_data = await asyncio.to_thread(self.queue.get, True, DEFAULT_VIDEO_JITTER_WAIT_S)
                got_item = True
            except std_queue.Empty:
                frame_data = None
                got_item = False

        if got_item and frame_data is None:
            logger.info(f"[QueueVideoTrack] Session {self.session_id} received end signal")
            self._stopped = True
            raise StopIteration

        if not got_item:
            # Fallback: repeat last frame (or black frame if none).
            if self._last_frame is None:
                img = np.zeros((64, 64, 3), dtype=np.uint8)
                self._last_frame = VideoFrame.from_ndarray(img, format="bgr24")
            video_frame = self._last_frame
        else:
            try:
                video_frame = deserialize_video_frame(frame_data)
                self._last_frame = video_frame
            except Exception as e:
                logger.error(f"[QueueVideoTrack] Failed to deserialize video frame: {e}")
                if self._last_frame is None:
                    img = np.zeros((64, 64, 3), dtype=np.uint8)
                    self._last_frame = VideoFrame.from_ndarray(img, format="bgr24")
                video_frame = self._last_frame

        video_frame.pts = self._timestamp
        video_frame.time_base = VIDEO_TIME_BASE
        self._timestamp += self._pts_step
        return video_frame
