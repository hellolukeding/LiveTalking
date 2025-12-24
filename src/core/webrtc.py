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
import time
from typing import Optional, Set, Union

import numpy as np
from aiortc import MediaStreamTrack
from av import AudioFrame, VideoFrame
from av.frame import Frame
from av.packet import Packet

from logger import logger as mylogger

AUDIO_PTIME = 0.020  # 20ms audio packetization
VIDEO_CLOCK_RATE = 90000
VIDEO_PTIME = 1.0 / 25  # 25fps = 40ms per frame
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)
SAMPLE_RATE = 16000
AUDIO_TIME_BASE = fractions.Fraction(1, SAMPLE_RATE)

logging.basicConfig()
logger = logging.getLogger(__name__)


class PlayerStreamTrack(MediaStreamTrack):
    """
    音视频轨道 - 简化稳定版
    """

    def __init__(self, player, kind):
        super().__init__()
        self.kind = kind
        self._player = player
        queue_size = 100 if kind == "audio" else 50
        self._queue = asyncio.Queue(maxsize=queue_size)
        self._last_frame = None
        self._start = None
        self._timestamp = 0
        
        if self.kind == 'video':
            self.framecount = 0
            self.lasttime = time.perf_counter()
            self.totaltime = 0

    async def recv(self) -> Union[Frame, Packet]:
        self._player._start(self)

        # 获取帧
        try:
            frame, eventpoint = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            if frame is not None:
                self._last_frame = frame
        except asyncio.TimeoutError:
            if self.readyState != "live":
                raise Exception("Track stopped")
            
            if self.kind == 'audio':
                audio = np.zeros((1, 320), dtype=np.int16)
                frame = AudioFrame.from_ndarray(audio, layout='mono', format='s16')
                frame.sample_rate = SAMPLE_RATE
            else:
                if self._last_frame is not None:
                    frame = self._last_frame
                else:
                    frame = VideoFrame.from_ndarray(
                        np.zeros((480, 640, 3), dtype=np.uint8), format="bgr24")
            eventpoint = {}

        if frame is None:
            self.stop()
            raise Exception("Frame is None")

        # 设置时间戳
        if self.kind == 'audio':
            if not hasattr(frame, 'sample_rate'):
                frame.sample_rate = SAMPLE_RATE
            samples = getattr(frame, 'samples', 320)

            if self._start is None:
                self._start = time.time()
                self._timestamp = 0
                mylogger.info(f'[AUDIO] Track started')

            frame.pts = self._timestamp
            frame.time_base = fractions.Fraction(1, SAMPLE_RATE)
            self._timestamp += samples
            # 音频不做节奏控制，让WebRTC自己处理
        else:
            if self._start is None:
                self._start = time.time()
                self._timestamp = 0
                mylogger.info(f'[VIDEO] Track started')

            frame.pts = self._timestamp
            frame.time_base = VIDEO_TIME_BASE
            self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)

            # 视频按帧率控制
            frame_count = self._timestamp // int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
            expected_time = self._start + frame_count * VIDEO_PTIME
            wait_time = expected_time - time.time()
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        if eventpoint and self._player is not None:
            self._player.notify(eventpoint)

        if self.kind == 'video':
            self.totaltime += (time.perf_counter() - self.lasttime)
            self.framecount += 1
            self.lasttime = time.perf_counter()
            if self.framecount == 100:
                mylogger.info(f"Video FPS: {self.framecount/self.totaltime:.2f}")
                self.framecount = 0
                self.totaltime = 0

        return frame

    def stop(self):
        super().stop()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except:
                pass
        if self._player is not None:
            self._player._stop(self)
            self._player = None


def player_worker_thread(quit_event, loop, container, audio_track, video_track):
    container.render(quit_event, loop, audio_track, video_track)


class HumanPlayer:

    def __init__(self, nerfreal, format=None, options=None, timeout=None, loop=False, decode=True):
        self.__thread = None
        self.__thread_quit = None
        self.__started: Set[PlayerStreamTrack] = set()
        
        self.__audio = PlayerStreamTrack(self, kind="audio")
        self.__video = PlayerStreamTrack(self, kind="video")
        self.__container = nerfreal

    def notify(self, eventpoint):
        if self.__container is not None:
            self.__container.notify(eventpoint)

    @property
    def audio(self) -> MediaStreamTrack:
        return self.__audio

    @property
    def video(self) -> MediaStreamTrack:
        return self.__video

    def _start(self, track: PlayerStreamTrack) -> None:
        self.__started.add(track)
        mylogger.info(f"[HumanPlayer] Track started: {track.kind}")

        if self.__thread is None:
            self.__thread_quit = asyncio.Event() if False else __import__('threading').Event()
            self.__thread = __import__('threading').Thread(
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
            mylogger.info("[HumanPlayer] Worker thread started")

    def _stop(self, track: PlayerStreamTrack) -> None:
        self.__started.discard(track)
        mylogger.info(f"[HumanPlayer] Track stopped: {track.kind}")

        if not self.__started and self.__thread is not None:
            self.__thread_quit.set()
            self.__thread.join()
            self.__thread = None

        if not self.__started and self.__container is not None:
            self.__container = None
