#!/usr/bin/env python3
"""
简化的音频同步修复方案
核心原则：只在WebRTC的recv方法中做时间控制，其他地方不做时间控制
"""

import asyncio
import time

import numpy as np
from av import AudioFrame


# 1. WebRTC recv方法 - 唯一的时间控制点
async def recv_audio_fixed(self):
    """修复后的WebRTC音频接收方法"""

    # 获取音频帧
    try:
        frame, eventpoint = await asyncio.wait_for(self._queue.get(), timeout=1.0)
    except asyncio.TimeoutError:
        if self.readyState != "live":
            raise Exception("Track stopped")
        # 返回静音帧
        audio = np.zeros((1, 320), dtype=np.int16)
        frame = AudioFrame.from_ndarray(audio, layout='mono', format='s16')
        frame.sample_rate = 16000
        eventpoint = {}

    if frame is None:
        self.stop()
        raise Exception

    # 确保音频帧属性正确
    if not hasattr(frame, 'sample_rate'):
        frame.sample_rate = 16000

    # 初始化时间基准（只做一次）
    if not hasattr(self, "_start"):
        self._start = time.time()
        self._timestamp = 0
        self.current_frame_count = 0

    # 计算时间戳
    n_samples = frame.samples if hasattr(frame, 'samples') else 320
    frame.pts = self._timestamp
    frame.time_base = fractions.Fraction(1, frame.sample_rate)

    # 推进时间戳
    self._timestamp += n_samples
    self.current_frame_count += 1

    # 精确时间控制 - 基于帧数
    expected_time = self._start + (self.current_frame_count * 0.020)
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

    return frame

# 2. TTS音频生成 - 不做时间控制，只负责生成


def tts_put_audio_frame(self, audio_chunk, eventpoint):
    """TTS生成音频帧，直接放入队列"""
    # 确保格式正确
    if not isinstance(audio_chunk, np.ndarray):
        return

    # 转换为int16
    frame = (audio_chunk * 32767).astype(np.int16)

    # 创建AudioFrame
    if frame.ndim == 1:
        frame_2d = frame.reshape(1, -1)
    else:
        frame_2d = frame.reshape(1, -1)

    new_frame = AudioFrame.from_ndarray(frame_2d, layout='mono', format='s16')
    new_frame.sample_rate = 16000
    new_frame.samples = 320  # 确保设置samples属性

    # 直接放入WebRTC队列（不做时间控制）
    if hasattr(self, 'audio_track') and self.audio_track:
        try:
            self.audio_track._queue.put_nowait((new_frame, eventpoint))
        except asyncio.QueueFull:
            # 队列满，丢弃旧帧
            try:
                self.audio_track._queue.get_nowait()
                self.audio_track._queue.put_nowait((new_frame, eventpoint))
            except:
                pass

# 3. ASR处理 - 不做时间控制


def asr_process(self):
    """ASR处理音频，不做时间控制"""
    # 只负责特征提取，不控制时间
    pass

# 4. render方法 - 不做时间控制


def render_fixed(self, quit_event, loop, audio_track, video_track):
    """修复后的render方法 - 移除所有时间控制"""

    # 初始化
    self.init_customindex()
    self.tts.render(quit_event, audio_track, loop)

    # 启动推理线程
    infer_thread = Thread(target=self.inference_loop, args=(quit_event,))
    infer_thread.start()

    # 启动处理线程
    process_thread = Thread(target=self.process_frames, args=(
        quit_event, loop, audio_track, video_track))
    process_thread.start()

    # 主循环 - 只负责调度，不做时间控制
    while not quit_event.is_set():
        # 简单的循环，不做复杂的时间控制
        time.sleep(0.01)  # 10ms的循环间隔

    # 清理
    infer_thread.join()
    process_thread.join()


print("简化的音频同步修复方案")
print("核心原则：")
print("1. 只在WebRTC的recv方法中做时间控制")
print("2. TTS/ASR只负责生成和处理，不控制时间")
print("3. render方法只负责调度，不控制时间")
print("4. 通过队列大小动态调整播放速度")
