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

import queue
import time
from queue import Queue

import numpy as np
import torch.multiprocessing as mp

from basereal import BaseReal
import os


class BaseASR:
    def __init__(self, opt, parent: BaseReal = None):
        self.opt = opt
        self.parent = parent

        self.fps = opt.fps  # 20 ms per frame
        self.sample_rate = 16000
        # 320 samples per chunk (20ms * 16000 / 1000)
        self.chunk = self.sample_rate // self.fps
        self.queue = Queue()
        self.output_queue = mp.Queue()

        self.batch_size = opt.batch_size

        self.frames = []
        self.stride_left_size = opt.l
        self.stride_right_size = opt.r
        # self.context_size = 10
        self.feat_queue = mp.Queue(2)

        # self.warm_up()

    def flush_talk(self):
        self.queue.queue.clear()

    def put_audio_frame(self, audio_chunk, datainfo: dict):  # 16khz 20ms pcm
        self.queue.put((audio_chunk, datainfo))

    # return frame:audio pcm; type: 0-normal speak, 1-silence; eventpoint:custom event sync with audio
    def get_audio_frame(self):
        # This function is called in tight loops (e.g. LipASR.run_step()).
        # When TTS is idle, using a per-frame 25ms blocking timeout slows down the whole pipeline
        # and caps video FPS (~20fps for wav2lip batch_size=16). To keep video smooth at 25fps,
        # we switch to a paced silence mode when no audio has arrived recently.
        #
        # During active speech we still keep a slightly longer timeout (25ms) to avoid frequent
        # timeouts that can cause audible artifacts.
        frame_period_s = 1.0 / float(self.fps) if self.fps else 0.02
        try:
            idle_threshold_s = float(os.getenv("ASR_IDLE_THRESHOLD_MS", "200")) / 1000.0
        except Exception:
            idle_threshold_s = 0.2  # 200ms

        now = time.perf_counter()
        last_audio_in = None
        try:
            if self.parent is not None:
                last_audio_in = getattr(self.parent, "_last_audio_in_time", None)
        except Exception:
            last_audio_in = None

        is_idle = last_audio_in is not None and (now - last_audio_in) > idle_threshold_s

        if is_idle:
            # Idle: generate paced silence/custom-audio at 20ms per frame without blocking waits.
            if self.parent and self.parent.curr_state > 1:  # 播放自定义音频
                time.sleep(frame_period_s)
                frame = self.parent.get_audio_stream(self.parent.curr_state)
                type = self.parent.curr_state
                eventpoint = None
                return frame, type, eventpoint

            time.sleep(frame_period_s)
            frame = np.zeros(self.chunk, dtype=np.float32)
            type = 1
            eventpoint = None
            return frame, type, eventpoint

        # Active: wait a bit longer than 20ms to tolerate scheduling jitter.
        try:
            frame, eventpoint = self.queue.get(block=True, timeout=0.025)
            type = 0
        except queue.Empty:
            if self.parent and self.parent.curr_state > 1:  # 播放自定义音频
                frame = self.parent.get_audio_stream(self.parent.curr_state)
                type = self.parent.curr_state
            else:
                frame = np.zeros(self.chunk, dtype=np.float32)
                type = 1
            eventpoint = None

        return frame, type, eventpoint

    # return frame:audio pcm; type: 0-normal speak, 1-silence; eventpoint:custom event sync with audio
    def get_audio_out(self):
        return self.output_queue.get()

    def warm_up(self):
        for _ in range(self.stride_left_size + self.stride_right_size):
            audio_frame, type, eventpoint = self.get_audio_frame()
            self.frames.append(audio_frame)
            self.output_queue.put((audio_frame, type, eventpoint))
        for _ in range(self.stride_left_size):
            self.output_queue.get()

    def run_step(self):
        pass

    def get_next_feat(self, block, timeout):
        return self.feat_queue.get(block, timeout)
