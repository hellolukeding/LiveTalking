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
import glob
import math
import os
import queue
import subprocess
import time
from fractions import Fraction
from io import BytesIO
from queue import Queue
from threading import Event, Thread

import av
import cv2
import numpy as np
import resampy
import soundfile as sf
import torch
from av import AudioFrame, VideoFrame
from tqdm import tqdm

from logger import logger
from ttsreal import (XTTS, AzureTTS, CosyVoiceTTS, DoubaoTTS, EdgeTTS, FishTTS,
                     IndexTTS2, SovitsTTS, TencentTTS)


def read_imgs(img_list):
    frames = []
    logger.debug('reading images...')
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames


def play_audio(quit_event, queue):
    import pyaudio
    p = pyaudio.PyAudio()
    stream = p.open(
        rate=16000,
        channels=1,
        format=8,
        output=True,
        output_device_index=1,
    )
    stream.start_stream()
    # while queue.qsize() <= 0:
    #     time.sleep(0.1)
    while not quit_event.is_set():
        stream.write(queue.get(block=True))
    stream.close()


class BaseReal:
    def __init__(self, opt):
        self.opt = opt
        self.sample_rate = 16000
        # 320 samples per chunk (20ms * 16000 / 1000)
        self.chunk = self.sample_rate // opt.fps
        self.sessionid = self.opt.sessionid

        if opt.tts == "doubao":
            self.tts = DoubaoTTS(opt, self)
        elif opt.tts == "edgetts":
            self.tts = EdgeTTS(opt, self)
        elif opt.tts == "gpt-sovits":
            self.tts = SovitsTTS(opt, self)
        elif opt.tts == "xtts":
            self.tts = XTTS(opt, self)
        elif opt.tts == "cosyvoice":
            self.tts = CosyVoiceTTS(opt, self)
        elif opt.tts == "fishtts":
            self.tts = FishTTS(opt, self)
        elif opt.tts == "tencent":
            self.tts = TencentTTS(opt, self)
        elif opt.tts == "indextts2":
            self.tts = IndexTTS2(opt, self)
        elif opt.tts == "azuretts":
            self.tts = AzureTTS(opt, self)
        else:
            # 默认使用doubao
            self.tts = DoubaoTTS(opt, self)

        self.speaking = False

        self.recording = False
        self._record_video_pipe = None
        self._record_audio_pipe = None
        self.width = self.height = 0

        self.curr_state = 0
        self.custom_img_cycle = {}
        self.custom_audio_cycle = {}
        self.custom_audio_index = {}
        self.custom_index = {}
        self.custom_opt = {}
        self.__loadcustom()
        self.datachannel = None
        self.loop = None
        self.audio_track = None  # WebRTC 音频轨道引用

        # Pending audio frames queued when audio_track or its event loop is not ready
        # Use a thread-safe list to buffer frames and flush later when possible
        import threading
        self._pending_audio = []  # list of (AudioFrame, datainfo)
        self._pending_audio_lock = threading.Lock()

    def send_custom_msg(self, msg):
        if self.datachannel:
            logger.info(
                f"Sending custom msg: {msg}, state: {self.datachannel.readyState}")
            if self.datachannel.readyState == "open":
                if self.loop:
                    self.loop.call_soon_threadsafe(self.datachannel.send, msg)
                else:
                    self.datachannel.send(msg)
        else:
            logger.debug(f"No datachannel to send msg: {msg}")

    def put_msg_txt(self, msg, datainfo: dict = {}):
        self.tts.put_msg_txt(msg, datainfo)
        self.send_custom_msg(msg)

    def put_audio_frame(self, audio_chunk, datainfo: dict = {}):  # 16khz 20ms pcm
        """音频帧转发 - 简化版"""
        # 转发给ASR（口型驱动）
        if hasattr(self, 'asr'):
            try:
                self.asr.put_audio_frame(audio_chunk, datainfo)
            except Exception:
                pass
        elif hasattr(self, 'lip_asr'):
            try:
                self.lip_asr.put_audio_frame(audio_chunk, datainfo)
            except Exception:
                pass

        # 转发给WebRTC
        try:
            if not isinstance(audio_chunk, np.ndarray):
                return

            # 简单直接的转换
            frame = np.clip(audio_chunk * 32767, -32768, 32767).astype(np.int16)
            
            # 确保320样本（20ms @ 16kHz）
            if len(frame) < 320:
                padded = np.zeros(320, dtype=np.int16)
                padded[:len(frame)] = frame
                frame = padded
            elif len(frame) > 320:
                frame = frame[:320]

            frame_2d = frame.reshape(1, -1)
            new_frame = AudioFrame.from_ndarray(frame_2d, layout='mono', format='s16')
            new_frame.sample_rate = 16000

            if not (hasattr(self, 'audio_track') and self.audio_track):
                with self._pending_audio_lock:
                    self._pending_audio.append((new_frame, datainfo))
                return

            # 先 flush pending 帧
            if self._pending_audio:
                self._flush_pending_audio()

            if hasattr(self, 'loop') and self.loop and self.loop.is_running():
                try:
                    self.loop.call_soon_threadsafe(
                        self.audio_track._queue.put_nowait, (new_frame, datainfo))
                except Exception:
                    pass  # 队列满时丢弃
            else:
                with self._pending_audio_lock:
                    self._pending_audio.append((new_frame, datainfo))

        except Exception as e:
            logger.error(f"[BASE_REAL] Audio error: {e}")

    def _flush_pending_audio(self):
        """尝试把缓冲区中的帧 flush 到音轨队列中。"""
        if not hasattr(self, 'audio_track') or not self.audio_track:
            return
        with self._pending_audio_lock:
            pending = self._pending_audio
            self._pending_audio = []
        if not pending:
            return

        # 🆕 修复：优先使用self.loop
        queue_loop = getattr(self, 'loop', None)
        if queue_loop and queue_loop.is_running():
            sent = 0
            for f, d in pending:
                try:
                    queue_loop.call_soon_threadsafe(
                        self.audio_track._queue.put_nowait, (f, d))
                    sent += 1
                except Exception as e:
                    logger.warning(
                        f"[BASE_REAL] Failed to flush pending audio frame: {e}")
            logger.info(
                f"[BASE_REAL] Flushed {sent} pending audio frames to track")
        else:
            # 如果仍然没有事件循环，则重新放回缓冲区
            with self._pending_audio_lock:
                self._pending_audio = pending + self._pending_audio
            logger.debug(
                "[BASE_REAL] Could not flush pending audio: queue loop not running")

    def put_audio_file(self, filebyte, datainfo: dict = {}):
        input_stream = BytesIO(filebyte)
        stream = self.__create_bytes_stream(input_stream)
        streamlen = stream.shape[0]
        idx = 0
        while streamlen >= self.chunk:  # and self.state==State.RUNNING
            self.put_audio_frame(stream[idx:idx+self.chunk], datainfo)
            streamlen -= self.chunk
            idx += self.chunk

    def __create_bytes_stream(self, byte_stream):
        # byte_stream=BytesIO(buffer)
        stream, sample_rate = sf.read(byte_stream)  # [T*sample_rate,] float64
        logger.debug(f'[INFO]put audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.debug(
                f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]

        if sample_rate != self.sample_rate and stream.shape[0] > 0:
            logger.debug(
                f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(
                x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream

    def flush_talk(self):
        self.tts.flush_talk()
        # 兼容不同的ASR实现
        if hasattr(self, 'asr'):
            self.asr.flush_talk()
        elif hasattr(self, 'lip_asr'):
            self.lip_asr.flush_talk()

    def is_speaking(self) -> bool:
        return self.speaking

    def __loadcustom(self):
        for item in self.opt.customopt:
            logger.debug(item)
            input_img_list = glob.glob(os.path.join(
                item['imgpath'], '*.[jpJP][pnPN]*[gG]'))
            input_img_list = sorted(input_img_list, key=lambda x: int(
                os.path.splitext(os.path.basename(x))[0]))
            self.custom_img_cycle[item['audiotype']
                                  ] = read_imgs(input_img_list)
            self.custom_audio_cycle[item['audiotype']], sample_rate = sf.read(
                item['audiopath'], dtype='float32')
            self.custom_audio_index[item['audiotype']] = 0
            self.custom_index[item['audiotype']] = 0
            self.custom_opt[item['audiotype']] = item

    def init_customindex(self):
        self.curr_state = 0
        for key in self.custom_audio_index:
            self.custom_audio_index[key] = 0
        for key in self.custom_index:
            self.custom_index[key] = 0

    def notify(self, eventpoint):
        logger.debug("notify:%s", eventpoint)

    def start_recording(self):
        """开始录制视频"""
        if self.recording:
            return

        command = ['ffmpeg',
                   '-y', '-an',
                   '-f', 'rawvideo',
                   '-vcodec', 'rawvideo',
                   '-pix_fmt', 'bgr24',  # 像素格式
                   '-s', "{}x{}".format(self.width, self.height),
                   '-r', str(25),
                   '-i', '-',
                   '-pix_fmt', 'yuv420p',
                   '-vcodec', "h264",
                   # '-f' , 'flv',
                   f'temp{self.opt.sessionid}.mp4']
        self._record_video_pipe = subprocess.Popen(
            command, shell=False, stdin=subprocess.PIPE)

        acommand = ['ffmpeg',
                    '-y', '-vn',
                    '-f', 's16le',
                    # '-acodec','pcm_s16le',
                    '-ac', '1',
                    '-ar', '16000',
                    '-i', '-',
                    '-acodec', 'aac',
                    # '-f' , 'wav',
                    f'temp{self.opt.sessionid}.aac']
        self._record_audio_pipe = subprocess.Popen(
            acommand, shell=False, stdin=subprocess.PIPE)

        self.recording = True
        # self.recordq_video.queue.clear()
        # self.recordq_audio.queue.clear()
        # self.container = av.open(path, mode="w")

        # process_thread = Thread(target=self.record_frame, args=())
        # process_thread.start()

    def record_video_data(self, image):
        if self.width == 0:
            print("image.shape:", image.shape)
            self.height, self.width, _ = image.shape
        if self.recording:
            self._record_video_pipe.stdin.write(image.tostring())

    def record_audio_data(self, frame):
        if self.recording:
            self._record_audio_pipe.stdin.write(frame.tostring())

    # def record_frame(self):
    #     videostream = self.container.add_stream("libx264", rate=25)
    #     videostream.codec_context.time_base = Fraction(1, 25)
    #     audiostream = self.container.add_stream("aac")
    #     audiostream.codec_context.time_base = Fraction(1, 16000)
    #     init = True
    #     framenum = 0
    #     while self.recording:
    #         try:
    #             videoframe = self.recordq_video.get(block=True, timeout=1)
    #             videoframe.pts = framenum #int(round(framenum*0.04 / videostream.codec_context.time_base))
    #             videoframe.dts = videoframe.pts
    #             if init:
    #                 videostream.width = videoframe.width
    #                 videostream.height = videoframe.height
    #                 init = False
    #             for packet in videostream.encode(videoframe):
    #                 self.container.mux(packet)
    #             for k in range(2):
    #                 audioframe = self.recordq_audio.get(block=True, timeout=1)
    #                 audioframe.pts = int(round((framenum*2+k)*0.02 / audiostream.codec_context.time_base))
    #                 audioframe.dts = audioframe.pts
    #                 for packet in audiostream.encode(audioframe):
    #                     self.container.mux(packet)
    #             framenum += 1
    #         except queue.Empty:
    #             print('record queue empty,')
    #             continue
    #         except Exception as e:
    #             print(e)
    #             #break
    #     for packet in videostream.encode(None):
    #         self.container.mux(packet)
    #     for packet in audiostream.encode(None):
    #         self.container.mux(packet)
    #     self.container.close()
    #     self.recordq_video.queue.clear()
    #     self.recordq_audio.queue.clear()
    #     print('record thread stop')

    def stop_recording(self):
        """停止录制视频"""
        if not self.recording:
            return
        self.recording = False
        self._record_video_pipe.stdin.close()  # wait()
        self._record_video_pipe.wait()
        self._record_audio_pipe.stdin.close()
        self._record_audio_pipe.wait()
        cmd_combine_audio = f"ffmpeg -y -i temp{self.opt.sessionid}.aac -i temp{self.opt.sessionid}.mp4 -c:v copy -c:a copy data/record.mp4"
        os.system(cmd_combine_audio)
        # os.remove(output_path)

    def mirror_index(self, size, index):
        # size = len(self.coord_list_cycle)
        turn = index // size
        res = index % size
        if turn % 2 == 0:
            return res
        else:
            return size - res - 1

    def get_audio_stream(self, audiotype):
        idx = self.custom_audio_index[audiotype]
        stream = self.custom_audio_cycle[audiotype][idx:idx+self.chunk]
        self.custom_audio_index[audiotype] += self.chunk
        if self.custom_audio_index[audiotype] >= self.custom_audio_cycle[audiotype].shape[0]:
            self.curr_state = 1  # 当前视频不循环播放，切换到静音状态
        return stream

    def set_custom_state(self, audiotype, reinit=True):
        print('set_custom_state:', audiotype)
        if self.custom_audio_index.get(audiotype) is None:
            return
        self.curr_state = audiotype
        if reinit:
            self.custom_audio_index[audiotype] = 0
            self.custom_index[audiotype] = 0

    def process_frames(self, quit_event, loop=None, audio_track=None, video_track=None):
        logger.debug(
            f"[PROCESS_FRAMES] Starting process_frames for session {self.sessionid}")
        logger.debug(
            f"[PROCESS_FRAMES] Transport: {self.opt.transport}, Loop: {loop is not None}")

        enable_transition = False  # 设置为False禁用过渡效果，True启用

        if enable_transition:
            _last_speaking = False
            _transition_start = time.time()
            _transition_duration = 0.1  # 过渡时间
            _last_silent_frame = None  # 静音帧缓存
            _last_speaking_frame = None  # 说话帧缓存

        if self.opt.transport == 'virtualcam':
            logger.debug(f"[PROCESS_FRAMES] Using virtualcam transport")
            import pyvirtualcam
            vircam = None

            audio_tmp = queue.Queue(maxsize=3000)
            audio_thread = Thread(target=play_audio, args=(
                quit_event, audio_tmp,), daemon=True, name="pyaudio_stream")
            audio_thread.start()
        else:
            logger.debug(f"[PROCESS_FRAMES] Using WebRTC transport")
            if audio_track is None:
                logger.error("[PROCESS_FRAMES] Audio track is None!")
            if video_track is None:
                logger.error("[PROCESS_FRAMES] Video track is None!")
            if loop is None:
                logger.error("[PROCESS_FRAMES] Event loop is None!")

        frame_count = 0
        last_log_time = time.time()

        while not quit_event.is_set():
            try:
                res_frame, idx, audio_frames = self.res_frame_queue.get(
                    block=True, timeout=1)
                frame_count += 1

                # Log frame processing status every 2 seconds
                if time.time() - last_log_time > 2:
                    logger.debug(
                        f"[PROCESS_FRAMES] Processing frames: count={frame_count}, session={self.sessionid}")
                    logger.debug(
                        f"[PROCESS_FRAMES] Audio queue size: {self.res_frame_queue.qsize()}")
                    last_log_time = time.time()
                    frame_count = 0

            except queue.Empty:
                logger.debug(
                    f"[PROCESS_FRAMES] Queue empty, waiting for frames...")
                continue
            except Exception as e:
                logger.debug(
                    f"[PROCESS_FRAMES] Error getting frame from queue: {str(e)}")
                continue

            # Log audio frame info
            if audio_frames and len(audio_frames) > 0:
                audio_info = [(f"frame_{i}", type, eventpoint)
                              for i, (frame, type, eventpoint) in enumerate(audio_frames)]
                logger.debug(f"[PROCESS_FRAMES] Audio frames: {audio_info}")

            if enable_transition:
                # 检测状态变化
                current_speaking = not (
                    audio_frames[0][1] != 0 and audio_frames[1][1] != 0)
                if current_speaking != _last_speaking:
                    logger.debug(
                        f"[PROCESS_FRAMES] 状态切换：{'说话' if _last_speaking else '静音'} → {'说话' if current_speaking else '静音'}")
                    _transition_start = time.time()
                _last_speaking = current_speaking

            if audio_frames[0][1] != 0 and audio_frames[1][1] != 0:  # 全为静音数据，只需要取fullimg
                self.speaking = False
                audiotype = audio_frames[0][1]

                if audiotype != 1:  # 非默认静音状态
                    logger.debug(
                        f"[PROCESS_FRAMES] Custom audio type: {audiotype}")

                if self.custom_index.get(audiotype) is not None:  # 有自定义视频
                    mirindex = self.mirror_index(
                        len(self.custom_img_cycle[audiotype]), self.custom_index[audiotype])
                    target_frame = self.custom_img_cycle[audiotype][mirindex]
                    self.custom_index[audiotype] += 1
                    logger.debug(
                        f"[PROCESS_FRAMES] Using custom frame, index: {mirindex}")
                else:
                    target_frame = self.frame_list_cycle[idx]
                    logger.debug(
                        f"[PROCESS_FRAMES] Using default frame, idx: {idx}")

                if enable_transition:
                    # 说话→静音过渡
                    if time.time() - _transition_start < _transition_duration and _last_speaking_frame is not None:
                        alpha = min(
                            1.0, (time.time() - _transition_start) / _transition_duration)
                        combine_frame = cv2.addWeighted(
                            _last_speaking_frame, 1-alpha, target_frame, alpha, 0)
                    else:
                        combine_frame = target_frame
                    # 缓存静音帧
                    _last_silent_frame = combine_frame.copy()
                else:
                    combine_frame = target_frame
            else:
                self.speaking = True
                logger.debug(
                    f"[PROCESS_FRAMES] Speaking state, processing frame {idx}")

                try:
                    current_frame = self.paste_back_frame(res_frame, idx)
                except Exception as e:
                    logger.debug(
                        f"[PROCESS_FRAMES] paste_back_frame error: {e}")
                    continue

                if enable_transition:
                    # 静音→说话过渡
                    if time.time() - _transition_start < _transition_duration and _last_silent_frame is not None:
                        alpha = min(
                            1.0, (time.time() - _transition_start) / _transition_duration)
                        combine_frame = cv2.addWeighted(
                            _last_silent_frame, 1-alpha, current_frame, alpha, 0)
                    else:
                        combine_frame = current_frame
                    # 缓存说话帧
                    _last_speaking_frame = combine_frame.copy()
                else:
                    combine_frame = current_frame

            # cv2.putText(combine_frame, "LiveTalking", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (128,128,128), 1)
            if self.opt.transport == 'virtualcam':
                if vircam == None:
                    height, width, _ = combine_frame.shape
                    logger.debug(
                        f"[PROCESS_FRAMES] Initializing virtualcam: {width}x{height}")
                    vircam = pyvirtualcam.Camera(
                        width=width, height=height, fps=25, fmt=pyvirtualcam.PixelFormat.BGR, print_fps=True)
                vircam.send(combine_frame)
                logger.debug(f"[PROCESS_FRAMES] Sent frame to virtualcam")
            else:  # webrtc
                try:
                    image = combine_frame
                    new_frame = VideoFrame.from_ndarray(image, format="bgr24")
                    if video_track and video_track._queue:
                        # 🆕 修复：使用call_soon_threadsafe + put_nowait，避免阻塞提高FPS
                        try:
                            loop.call_soon_threadsafe(
                                video_track._queue.put_nowait, (new_frame, None))
                        except Exception as queue_err:
                            # 队列满时丢弃帧，避免阻塞
                            logger.debug(f"[PROCESS_FRAMES] Video queue full, dropping frame")
                    else:
                        logger.debug(
                            f"[PROCESS_FRAMES] Video track or queue is None!")
                except Exception as e:
                    logger.debug(
                        f"[PROCESS_FRAMES] Failed to send video frame: {str(e)}")

            self.record_video_data(combine_frame)

            # 🆕 修复：移除process_frames中的音频处理逻辑
            # 音频处理已经在put_audio_frame中完成，这里不需要重复处理
            # 这避免了音频被处理两次导致的速度过快问题

            if self.opt.transport == 'virtualcam':
                vircam.sleep_until_next_frame()

        logger.debug(f"[PROCESS_FRAMES] Quit signal received, cleaning up...")

        if self.opt.transport == 'virtualcam':
            audio_thread.join()
            if vircam:
                vircam.close()
            logger.debug(f"[PROCESS_FRAMES] Virtualcam closed")

        logger.debug(
            f"[PROCESS_FRAMES] process_frames thread stopped for session {self.sessionid}")

    # def process_custom(self,audiotype:int,idx:int):
    #     if self.curr_state!=audiotype: #从推理切到口播
    #         if idx in self.switch_pos:  #在卡点位置可以切换
    #             self.curr_state=audiotype
    #             self.custom_index=0
    #     else:
    #         self.custom_index+=1
