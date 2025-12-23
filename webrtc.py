###############################################################################
#  Copyright (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking
#  email: lipku@foxmail.com
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import asyncio
import fractions
import json
import logging
import threading
import time
from typing import Dict, Optional, Set, Tuple, Union

import numpy as np
from aiortc import MediaStreamTrack
from av import AudioFrame
from av.frame import Frame
from av.packet import Packet

from logger import logger as mylogger

AUDIO_PTIME = 0.020  # 20ms audio packetization
VIDEO_CLOCK_RATE = 90000
VIDEO_PTIME = 0.040  # 1 / 25  # 30fps
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)
SAMPLE_RATE = 16000
AUDIO_TIME_BASE = fractions.Fraction(1, SAMPLE_RATE)

# from aiortc.contrib.media import MediaPlayer, MediaRelay
# from aiortc.rtcrtpsender import RTCRtpSender

logging.basicConfig()
logger = logging.getLogger(__name__)


class PlayerStreamTrack(MediaStreamTrack):
    """
    A video track that returns an animated flag.
    """

    def __init__(self, player, kind):
        super().__init__()  # don't forget this!
        self.kind = kind
        self._player = player
        # 🆕 修复：调整队列容量，避免过大导致延迟
        # 音频：200帧 = 4秒缓冲，视频：100帧 = 4秒缓冲
        queue_size = 200 if kind == "audio" else 100
        self._queue = asyncio.Queue(maxsize=queue_size)
        self.timelist = []  # 记录最近包的时间戳
        self.current_frame_count = 0
        if self.kind == 'video':
            self.framecount = 0
            self.lasttime = time.perf_counter()
            self.totaltime = 0

    _start: float
    _timestamp: int

    async def next_timestamp(self) -> Tuple[int, fractions.Fraction]:
        if self.readyState != "live":
            raise Exception

        if self.kind == 'video':
            if hasattr(self, "_timestamp"):
                # self._timestamp = (time.time()-self._start) * VIDEO_CLOCK_RATE
                self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
                self.current_frame_count += 1
                wait = self._start + self.current_frame_count * VIDEO_PTIME - time.time()
                # wait = self.timelist[0] + len(self.timelist)*VIDEO_PTIME - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                # if len(self.timelist)>=100:
                #     self.timelist.pop(0)
                # self.timelist.append(time.time())
            else:
                self._start = time.time()
                self._timestamp = 0
                self.timelist.append(self._start)
                mylogger.info('video start:%f', self._start)
            return self._timestamp, VIDEO_TIME_BASE
        else:  # audio
            if hasattr(self, "_timestamp"):
                # self._timestamp = (time.time()-self._start) * SAMPLE_RATE
                self._timestamp += int(AUDIO_PTIME * SAMPLE_RATE)
                self.current_frame_count += 1
                wait = self._start + self.current_frame_count * AUDIO_PTIME - time.time()
                # wait = self.timelist[0] + len(self.timelist)*AUDIO_PTIME - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                # if len(self.timelist)>=200:
                #     self.timelist.pop(0)
                #     self.timelist.pop(0)
                # self.timelist.append(time.time())
            else:
                self._start = time.time()
                self._timestamp = 0
                self.timelist.append(self._start)
                mylogger.info('audio start:%f', self._start)
            return self._timestamp, AUDIO_TIME_BASE

    async def recv(self) -> Union[Frame, Packet]:
        # frame = self.frames[self.counter % 30]
        self._player._start(self)

        # 安全获取帧，避免阻塞
        try:
            frame, eventpoint = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            # 如果超时，检查是否需要停止
            if self.readyState != "live":
                raise Exception("Track stopped")
            # 返回静音帧避免卡死
            if self.kind == 'audio':
                audio = np.zeros((1, 320), dtype=np.int16)
                frame = AudioFrame.from_ndarray(
                    audio, layout='mono', format='s16')
                frame.sample_rate = 16000
                eventpoint = {}
            else:
                # 视频返回黑色帧
                frame = VideoFrame.from_ndarray(
                    np.zeros((480, 640, 3), dtype=np.uint8), format="bgr24")
                eventpoint = {}

        # 如果队列中放入的是 None，停止轨道
        if frame is None:
            self.stop()
            raise Exception

        # 音频时间戳处理
        if self.kind == 'audio':
            # 确保音频帧有正确的sample_rate和samples属性
            if not hasattr(frame, 'sample_rate'):
                frame.sample_rate = SAMPLE_RATE
            if not hasattr(frame, 'samples'):
                frame.samples = 320  # 20ms at 16kHz

            sample_rate = frame.sample_rate
            n_samples = frame.samples

            # 初始化时间基准
            if not hasattr(self, "_timestamp"):
                self._start = time.time()
                self._timestamp = 0
                self.current_frame_count = 0
                mylogger.info('audio start:%f', self._start)

            # 计算当前帧的PTS
            pts = self._timestamp
            frame.pts = pts
            frame.time_base = fractions.Fraction(1, sample_rate)

            # 推进时间戳
            self._timestamp += n_samples
            self.current_frame_count += 1

            # 精确时间控制 - 使用固定间隔
            expected_time = self._start + \
                (self.current_frame_count * AUDIO_PTIME)
            wait_time = expected_time - time.time()

            # 简单的等待逻辑
            if wait_time > 0:
                # 根据队列大小动态调整
                queue_size = self._queue.qsize()
                if queue_size > 40:
                    wait_time = min(wait_time, 0.005)
                elif queue_size > 20:
                    wait_time = min(wait_time, 0.01)

                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            elif wait_time < -0.1:
                mylogger.warning(
                    f"[WebRTC] Audio behind schedule: {wait_time:.3f}s")
        else:
            pts, time_base = await self.next_timestamp()
            frame.pts = pts
            frame.time_base = time_base

        if eventpoint and self._player is not None:
            self._player.notify(eventpoint)

        if self.kind == 'video':
            self.totaltime += (time.perf_counter() - self.lasttime)
            self.framecount += 1
            self.lasttime = time.perf_counter()
            if self.framecount == 100:
                mylogger.info(
                    f"------actual avg final fps:{self.framecount/self.totaltime:.4f}")
                self.framecount = 0
                self.totaltime = 0
        return frame

    def stop(self):
        super().stop()
        # Drain & delete remaining frames
        while not self._queue.empty():
            item = self._queue.get_nowait()
            del item
        if self._player is not None:
            self._player._stop(self)
            self._player = None


def player_worker_thread(
    quit_event,
    loop,
    container,
    audio_track,
    video_track
):
    container.render(quit_event, loop, audio_track, video_track)


class HumanPlayer:

    def __init__(
        self, nerfreal, format=None, options=None, timeout=None, loop=False, decode=True
    ):
        self.__thread: Optional[threading.Thread] = None
        self.__thread_quit: Optional[threading.Event] = None

        # examine streams
        self.__started: Set[PlayerStreamTrack] = set()
        self.__audio: Optional[PlayerStreamTrack] = None
        self.__video: Optional[PlayerStreamTrack] = None

        self.__audio = PlayerStreamTrack(self, kind="audio")
        self.__video = PlayerStreamTrack(self, kind="video")

        self.__container = nerfreal

    def notify(self, eventpoint):
        if self.__container is not None:
            self.__container.notify(eventpoint)

    @property
    def audio(self) -> MediaStreamTrack:
        """
        A :class:`aiortc.MediaStreamTrack` instance if the file contains audio.
        """
        return self.__audio

    @property
    def video(self) -> MediaStreamTrack:
        """
        A :class:`aiortc.MediaStreamTrack` instance if the file contains video.
        """
        return self.__video

    def _start(self, track: PlayerStreamTrack) -> None:
        self.__started.add(track)
        mylogger.info(
            f"[HumanPlayer] Track started: {track.kind}, total started: {len(self.__started)}")

        if self.__thread is None:
            mylogger.info(
                f"[HumanPlayer] Starting worker thread for {track.kind} track")
            self.__thread_quit = threading.Event()
            self.__thread = threading.Thread(
                name="media-player",
                target=player_worker_thread,
                args=(
                    self.__thread_quit,
                    asyncio.get_event_loop(),
                    self.__container,
                    self.__audio,
                    self.__video
                ),
            )
            self.__thread.start()
            mylogger.debug(f"[HumanPlayer] Worker thread started successfully")
        else:
            mylogger.debug(f"[HumanPlayer] Worker thread already running")

    def _stop(self, track: PlayerStreamTrack) -> None:
        self.__started.discard(track)
        mylogger.info(
            f"[HumanPlayer] Track stopped: {track.kind}, remaining: {len(self.__started)}")

        if not self.__started and self.__thread is not None:
            mylogger.debug(f"[HumanPlayer] Stopping worker thread")
            self.__thread_quit.set()
            self.__thread.join()
            self.__thread = None
            mylogger.debug(f"[HumanPlayer] Worker thread stopped")

        if not self.__started and self.__container is not None:
            mylogger.debug(f"[HumanPlayer] Clearing container reference")
            # self.__container.close()
            self.__container = None

    def __log_debug(self, msg: str, *args) -> None:
        mylogger.debug(f"HumanPlayer {msg}", *args)
