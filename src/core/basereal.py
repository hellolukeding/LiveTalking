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
import json
import math
import os
import queue
import subprocess
import threading
import time
from collections import deque
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
from logger import logger
from tqdm import tqdm
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
        self._last_audio_in_time = time.perf_counter()

        # 🚀 延迟初始化 TTS 以加快 /offer 响应速度
        # TTS 初始化可能涉及网络连接，放在 render() 中异步执行
        self._tts_initialized = False
        self._tts_lock = threading.Lock()
        self.tts = None

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

        # Runtime metrics
        self._video_drop_count = 0
        self._dropped_audio_frames = 0  # 丢帧统计

        # Pending audio frames queued when audio_track or its event loop is not ready
        # Use a thread-safe list to buffer frames and flush later when possible
        self._pending_audio = []  # list of (AudioFrame, datainfo)
        self._pending_audio_lock = threading.Lock()

        # Audio output A/V sync: delay audio output to align with video pipeline latency.
        # This delays only what we send to WebRTC audio_track; LipASR still receives audio immediately.
        try:
            self._audio_out_delay_s = float(os.getenv("AV_SYNC_DELAY_MS", "0")) / 1000.0
        except Exception:
            self._audio_out_delay_s = 0.0
        if self._audio_out_delay_s < 0:
            self._audio_out_delay_s = 0.0

        try:
            fps = int(getattr(opt, "fps", 50)) or 50
        except Exception:
            fps = 50
        self._audio_out_period_s = 1.0 / float(fps)

        self._audio_out_buffer = deque()  # deque[(due_time, AudioFrame, datainfo)]
        self._audio_out_lock = threading.Lock()
        self._audio_out_started = False
        self._audio_out_thread = None

    @property
    def _render_quit_event(self):
        """Store render quit event for external access"""
        return getattr(self, '__render_quit_event', None)

    @property
    def _infer_quit_event(self):
        """Store inference quit event for external access"""
        return getattr(self, '__infer_quit_event', None)

    @property
    def _process_quit_event(self):
        """Store process quit event for external access"""
        return getattr(self, '__process_quit_event', None)

    def stop_all_threads(self):
        """停止所有后台线程

        当连接异常断开时，需要主动停止所有后台线程以避免资源泄漏。
        包括：render主线程、infer_thread、process_thread、metrics_thread
        """
        logger.info(f"[BaseReal] stop_all_threads called for session {self.sessionid}")

        # 🆕 首先停止 TTS，避免产生新的音频数据
        try:
            if self.tts and hasattr(self.tts, 'stop'):
                logger.debug(f"[BaseReal] Stopping TTS for session {self.sessionid}")
                self.tts.stop()
        except Exception as e:
            logger.debug(f"[BaseReal] Error stopping TTS: {e}")

        # 停止所有退出事件
        render_quit = self._render_quit_event
        if render_quit:
            render_quit.set()
            logger.debug(f"[BaseReal] Set render_quit_event for session {self.sessionid}")

        infer_quit = self._infer_quit_event
        if infer_quit:
            infer_quit.set()
            logger.debug(f"[BaseReal] Set infer_quit_event for session {self.sessionid}")

        process_quit = self._process_quit_event
        if process_quit:
            process_quit.set()
            logger.debug(f"[BaseReal] Set process_quit_event for session {self.sessionid}")

        # 停止metrics线程
        try:
            self._metrics_running = False
        except Exception:
            pass

        # 🆕 停止 audio_out_worker
        try:
            self._audio_out_started = False
        except Exception:
            pass

        # 等待线程结束（带超时避免永久阻塞）
        infer_thread = getattr(self, '_infer_thread', None)
        if infer_thread and infer_thread.is_alive():
            infer_thread.join(timeout=5.0)
            if infer_thread.is_alive():
                logger.warning(f"[BaseReal] Infer thread still alive after timeout for session {self.sessionid}")

        process_thread = getattr(self, '_process_thread', None)
        if process_thread and process_thread.is_alive():
            process_thread.join(timeout=5.0)
            if process_thread.is_alive():
                logger.warning(f"[BaseReal] Process thread still alive after timeout for session {self.sessionid}")

        metrics_thread = getattr(self, '_metrics_thread', None)
        if metrics_thread and metrics_thread.is_alive():
            metrics_thread.join(timeout=1.0)

        audio_out_thread = getattr(self, '_audio_out_thread', None)
        if audio_out_thread and audio_out_thread.is_alive():
            audio_out_thread.join(timeout=1.0)

        # 🆕 清理 TTS 资源
        try:
            if self.tts and hasattr(self.tts, 'cleanup'):
                logger.debug(f"[BaseReal] Cleaning up TTS for session {self.sessionid}")
                self.tts.cleanup()
        except Exception as e:
            logger.debug(f"[BaseReal] Error cleaning up TTS: {e}")

        # 🆕 清理 ASR 资源
        try:
            if hasattr(self, 'asr') and self.asr and hasattr(self.asr, 'stop'):
                logger.debug(f"[BaseReal] Stopping ASR for session {self.sessionid}")
                self.asr.stop()
        except Exception as e:
            logger.debug(f"[BaseReal] Error stopping ASR: {e}")

        try:
            if hasattr(self, 'lip_asr') and self.lip_asr and hasattr(self.lip_asr, 'stop'):
                logger.debug(f"[BaseReal] Stopping LipASR for session {self.sessionid}")
                self.lip_asr.stop()
        except Exception as e:
            logger.debug(f"[BaseReal] Error stopping LipASR: {e}")

        logger.info(f"[BaseReal] stop_all_threads completed for session {self.sessionid}")

    def start_audio_out_worker(self, quit_event: Event):
        """
        Start a background worker that releases delayed audio frames at real-time cadence.
        Must be called from render() after loop/audio_track are set.
        """
        if self._audio_out_delay_s <= 0:
            return
        if self._audio_out_started:
            return
        self._audio_out_started = True
        self._audio_out_thread = Thread(
            target=self._audio_out_worker,
            args=(quit_event,),
            daemon=True,
            name=f"audio-out-{self.sessionid}",
        )
        self._audio_out_thread.start()

    def _enqueue_audio_out(self, frame: AudioFrame, datainfo: dict):
        due = time.perf_counter() + self._audio_out_delay_s
        with self._audio_out_lock:
            self._audio_out_buffer.append((due, frame, datainfo))

    def _audio_out_worker(self, quit_event: Event):
        next_send_time = time.perf_counter()
        while True:
            if quit_event.is_set():
                with self._audio_out_lock:
                    if not self._audio_out_buffer:
                        break

            now = time.perf_counter()
            if now < next_send_time:
                time.sleep(min(0.005, next_send_time - now))
                continue

            item = None
            with self._audio_out_lock:
                if self._audio_out_buffer and self._audio_out_buffer[0][0] <= now:
                    _, frame, datainfo = self._audio_out_buffer.popleft()
                    item = (frame, datainfo)

            if not item:
                time.sleep(0.005)
                continue

            # Best-effort push; if the queue is full, we drop to avoid backpressure.
            if hasattr(self, "audio_track") and self.audio_track and hasattr(self, "loop") and self.loop and self.loop.is_running():
                try:
                    self.loop.call_soon_threadsafe(
                        self.audio_track._queue.put_nowait, item)
                except Exception:
                    pass

            # Maintain real-time pacing (20ms per frame at 50fps).
            next_send_time = max(next_send_time + self._audio_out_period_s, time.perf_counter())

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

    def _ensure_tts_initialized(self):
        """延迟初始化 TTS（线程安全）"""
        if self._tts_initialized:
            return
        with self._tts_lock:
            if self._tts_initialized:
                return
            logger.info(f"[BaseReal] 延迟初始化 TTS: type={self.opt.tts}")
            tts_type = self.opt.tts
            if tts_type == "doubao":
                self.tts = DoubaoTTS(self.opt, self)
            elif tts_type == "edgetts":
                self.tts = EdgeTTS(self.opt, self)
            elif tts_type == "gpt-sovits":
                self.tts = SovitsTTS(self.opt, self)
            elif tts_type == "xtts":
                self.tts = XTTS(self.opt, self)
            elif tts_type == "cosyvoice":
                self.tts = CosyVoiceTTS(self.opt, self)
            elif tts_type == "fishtts":
                self.tts = FishTTS(self.opt, self)
            elif tts_type == "tencent":
                self.tts = TencentTTS(self.opt, self)
            elif tts_type == "indextts2":
                self.tts = IndexTTS2(self.opt, self)
            elif tts_type == "azuretts":
                self.tts = AzureTTS(self.opt, self)
            else:
                # 默认使用doubao
                self.tts = DoubaoTTS(self.opt, self)
            self._tts_initialized = True
            logger.info(f"[BaseReal] TTS 初始化完成")

    def put_msg_txt(self, msg, datainfo: dict = {}):
        self._ensure_tts_initialized()
        if self.tts:
            self.tts.put_msg_txt(msg, datainfo)
        self.send_custom_msg(msg)

    def put_audio_frame(self, audio_chunk, datainfo: dict = {}):  # 16khz 20ms pcm
        """音频帧转发给 ASR（口型驱动）"""
        self._last_audio_in_time = time.perf_counter()
        
        # 🔇 回声消除：TTS播放时不处理ASR，防止数字人听到自己的声音
        # curr_state > 1 表示正在播放自定义音频（TTS）
        if self.curr_state <= 1:  # 只在未播放TTS时处理ASR
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

    def _flush_pending_audio(self):
        """尝试把缓冲区中的帧 flush 到音轨队列中。"""
        if not hasattr(self, 'audio_track') or not self.audio_track:
            return
        with self._pending_audio_lock:
            pending = self._pending_audio
            self._pending_audio = []
        if not pending:
            return

        # If delay is enabled, enqueue pending frames into delayed buffer (worker will release them).
        if self._audio_out_delay_s > 0:
            for f, d in pending:
                self._enqueue_audio_out(f, d)
            return

        # 🆕 修复：优先使用self.loop
        queue_loop = getattr(self, 'loop', None)
        if queue_loop and queue_loop.is_running():
            sent = 0
            failed = []

            async def _try_put(q, item):
                try:
                    q.put_nowait(item)
                    return True
                except asyncio.QueueFull:
                    return False

            for f, d in pending:
                attempt = 0
                success = False
                # 尝试多次放入队列以处理短暂的队列满情况
                while attempt < 3 and not success:
                    attempt += 1
                    try:
                        fut = asyncio.run_coroutine_threadsafe(
                            _try_put(self.audio_track._queue, (f, d)), queue_loop)
                        ok = fut.result(timeout=0.5)
                        if ok:
                            sent += 1
                            success = True
                            break
                        else:
                            # 等待一小段时间再重试
                            time.sleep(0.01)
                    except Exception as e:
                        logger.warning(
                            f"[BASE_REAL] Failed to flush pending audio frame (attempt {attempt}): {e}")
                        time.sleep(0.01)
                if not success:
                    failed.append((f, d))

            # 如果有未发送的帧，放回_pending_audio头部
            if failed:
                with self._pending_audio_lock:
                    self._pending_audio = failed + self._pending_audio

            logger.info(
                f"[BASE_REAL] Flushed {sent} pending audio frames to track (remaining pending: {len(self._pending_audio)})")
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
        if self.tts:
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
        # 发送TTS完成信号到前端
        if eventpoint:
            try:
                # 确保 eventpoint 可以被 JSON 序列化
                if isinstance(eventpoint, dict):
                    # 清理不可序列化的值
                    clean_eventpoint = {k: v for k, v in eventpoint.items() 
                                        if isinstance(v, (str, int, float, bool, type(None)))}
                    msg = json.dumps(clean_eventpoint)
                else:
                    msg = json.dumps({"status": str(eventpoint)})
                self.send_custom_msg(msg)
            except (TypeError, ValueError) as e:
                logger.error(f"[NOTIFY] 序列化 eventpoint 失败: {e}")

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
            _last_speaking_frame = null  # 说话帧缓存

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
                logger.error("[PROCESS_LOGS] Event loop is None!")

        frame_count = 0
        last_log_time = time.time()

        while not quit_event.is_set():
            try:
                res_frame, idx, audio_frames = self.res_frame_queue.get(
                    block=True, timeout=1)
                frame_count += 1

                # Log frame processing status every 2 seconds
                current_time = time.time()
                if current_time - last_log_time > 2:
                    logger.debug(
                        f"[PROCESS_FRAMES] Processing frames: count={frame_count}, session={self.sessionid}")
                    logger.debug(
                        f"[PROCESS_FRAMES] Audio queue size: {self.res_frame_queue.qsize()}")
                    last_log_time = current_time
                    frame_count = 0

            except queue.Empty:
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
                            try:
                                self._video_drop_count += 1
                            except Exception:
                                pass
                            logger.debug(
                                f"[PROCESS_FRAMES] Video queue full, dropping frame (total_dropped={getattr(self, '_video_drop_count', 0)})")
                    else:
                        logger.debug(
                            f"[PROCESS_FRAMES] Video track or queue is None!")
                except Exception as e:
                    logger.debug(
                        f"[PROCESS_FRAMES] Failed to send video frame: {str(e)}")

            self.record_video_data(combine_frame)

            # 🔄 音频处理：遍历 audio_frames 并发送到 WebRTC
            for audio_frame in audio_frames:
                frame, type, eventpoint = audio_frame
                frame = (frame * 32767).astype(np.int16)

                if self.opt.transport == 'virtualcam':
                    audio_tmp.put(frame.tobytes())
                else:  # webrtc
                    new_frame = AudioFrame(format='s16', layout='mono', samples=frame.shape[0])
                    new_frame.planes[0].update(frame.tobytes())
                    new_frame.sample_rate = 16000
                    if audio_track and audio_track._queue:
                        loop.call_soon_threadsafe(
                            audio_track._queue.put_nowait, (new_frame, eventpoint))
                    else:
                        logger.debug("[PROCESS_FRAMES] Audio track or queue is None!")
                self.record_audio_data(frame)

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
