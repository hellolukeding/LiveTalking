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
import logging
import threading
import time
from typing import Tuple, Dict, Optional, Set, Union
from av.frame import Frame
from av.packet import Packet
from av import AudioFrame, VideoFrame
import numpy as np

from aiortc import MediaStreamTrack
from logger import logger as mylogger

AUDIO_PTIME = 0.020  # 20ms audio packetization
VIDEO_CLOCK_RATE = 90000
VIDEO_PTIME = 0.040  # 25fps = 40ms per frame
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)
SAMPLE_RATE = 16000
AUDIO_TIME_BASE = fractions.Fraction(1, SAMPLE_RATE)

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
        self._queue = asyncio.Queue(maxsize=10)
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
                self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
                self.current_frame_count += 1
                wait = self._start + self.current_frame_count * VIDEO_PTIME - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)
            else:
                self._start = time.time()
                self._timestamp = 0
                self.timelist.append(self._start)
                mylogger.info('video start:%f', self._start)
            return self._timestamp, VIDEO_TIME_BASE
        else:  # audio
            if hasattr(self, "_timestamp"):
                self._timestamp += int(AUDIO_PTIME * SAMPLE_RATE)
                self.current_frame_count += 1
                wait = self._start + self.current_frame_count * AUDIO_PTIME - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)
            else:
                self._start = time.time()
                self._timestamp = 0
                self.timelist.append(self._start)
                mylogger.info('audio start:%f', self._start)
            return self._timestamp, AUDIO_TIME_BASE

    async def recv(self) -> Union[Frame, Packet]:
        self._player._start(self)
        frame, eventpoint = await self._queue.get()
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        if eventpoint and self._player is not None:
            self._player.notify(eventpoint)
        if frame is None:
            self.stop()
            raise Exception
        if self.kind == 'video':
            self.totaltime += (time.perf_counter() - self.lasttime)
            self.framecount += 1
            self.lasttime = time.perf_counter()
            if self.framecount == 100:
                mylogger.info(f"------actual avg final fps:{self.framecount/self.totaltime:.4f}")
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
        self.__stopping = False  # 🆕 标记是否正在停止

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
        if self.__stopping:  # 🆕 如果正在停止，不允许启动
            return
        self.__started.add(track)
        if self.__thread is None:
            self.__log_debug("Starting worker thread")
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

    def _stop(self, track: PlayerStreamTrack) -> None:
        self.__started.discard(track)

        if not self.__started and self.__thread is not None:
            self.__log_debug("Stopping worker thread")
            self.__thread_quit.set()
            self.__thread.join(timeout=5.0)  # 🆕 添加超时，避免永久阻塞
            if self.__thread.is_alive():
                mylogger.warning(f"HumanPlayer worker thread did not stop in time")
            self.__thread = None

        if not self.__started and self.__container is not None:
            self.__container = None

    def stop_worker_thread(self):
        """🆕 主动停止 worker 线程（用于异常断开时）"""
        if self.__stopping:
            return
        self.__stopping = True

        # 停止所有 tracks
        if self.__audio:
            try:
                self.__audio.stop()
            except Exception:
                pass
        if self.__video:
            try:
                self.__video.stop()
            except Exception:
                pass

        # 确保线程停止
        if self.__thread is not None and self.__thread.is_alive():
            self.__log_debug("Force stopping worker thread")
            self.__thread_quit.set()
            self.__thread.join(timeout=5.0)
            if self.__thread.is_alive():
                mylogger.warning(f"HumanPlayer worker thread still alive after force stop")
            self.__thread = None

        # 清理容器引用
        self.__container = None

    def __log_debug(self, msg: str, *args) -> None:
        mylogger.debug(f"HumanPlayer {msg}", *args)
