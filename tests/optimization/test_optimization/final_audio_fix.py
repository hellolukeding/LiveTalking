#!/usr/bin/env python3
"""
最终音频修复方案
解决：噪音、卡顿、速度过快问题
"""

import asyncio
import time

import numpy as np
from av import AudioFrame


# 关键修复点
def fixed_doubao_stream_audio(self, audio_array, msg):
    """修复的DoubaoTTS流式音频处理"""
    text, textevent = msg
    streamlen = audio_array.shape[0]
    idx = 0
    first = True

    # 🆕 关键修复：使用缓冲区处理不完整的音频块
    buffer = np.array([], dtype=np.float32)

    frames_sent = 0

    while idx < streamlen and self.state == State.RUNNING:
        # 添加到缓冲区
        buffer = np.concatenate([buffer, audio_array[idx:idx+self.chunk]])

        # 从缓冲区取出完整的320样本块
        while len(buffer) >= self.chunk:
            audio_chunk = buffer[:self.chunk]
            buffer = buffer[self.chunk:]

            eventpoint = {}
            if first:
                eventpoint = {'status': 'start', 'text': text}
                eventpoint.update(**textevent)
                first = False

            # 直接发送，不填充静音
            self.parent.put_audio_frame(audio_chunk, eventpoint)
            frames_sent += 1

        idx += self.chunk

    # 处理缓冲区剩余数据
    if len(buffer) > 0 and self.state == State.RUNNING:
        # 填充静音到完整块（只在最后）
        padded_chunk = np.zeros(self.chunk, dtype=np.float32)
        padded_chunk[:len(buffer)] = buffer

        eventpoint = {'status': 'end', 'text': text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(padded_chunk, eventpoint)
        frames_sent += 1
    else:
        # 发送结束事件
        eventpoint = {'status': 'end', 'text': text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(
            np.zeros(self.chunk, np.float32), eventpoint)

    logger.debug(f"[DOUBAO_TTS] Stream completed, {frames_sent} frames sent")


def fixed_basereal_put_audio_frame(self, audio_chunk, datainfo):
    """修复的basereal音频处理"""
    # 确保音频数据格式正确
    if not isinstance(audio_chunk, np.ndarray):
        logger.error(
            f"[BASE_REAL] Invalid audio chunk type: {type(audio_chunk)}")
        return

    # 🆕 关键修复：不检查大小，直接转换
    # TTS应该已经生成了正确的320样本块

    # 转换为16-bit
    frame = (audio_chunk * 32767).astype(np.int16)

    # 创建音频帧
    if frame.ndim == 1:
        frame_2d = frame.reshape(1, -1)
    else:
        frame_2d = frame.reshape(1, -1)

    try:
        new_frame = AudioFrame.from_ndarray(
            frame_2d, layout='mono', format='s16')
        new_frame.sample_rate = 16000
        # samples属性自动计算，不需要手动设置
    except Exception as e:
        logger.error(f"[BASE_REAL] Failed to create AudioFrame: {e}")
        return

    # 如果 audio_track 未设置，则缓冲
    if not (hasattr(self, 'audio_track') and self.audio_track):
        with self._pending_audio_lock:
            self._pending_audio.append((new_frame, datainfo))
        logger.debug("[BASE_REAL] Audio track not ready, buffered")
        return

    # 简单的队列检查
    queue_size = self.audio_track._queue.qsize()
    if queue_size > 60:  # 队列过大，丢弃
        logger.warning(
            f"[BASE_REAL] Queue too large ({queue_size}), dropping frame")
        return

    # 直接放入队列
    queue_loop = getattr(self.audio_track._queue, '_loop', None)
    if queue_loop and queue_loop.is_running():
        try:
            queue_loop.call_soon_threadsafe(
                self.audio_track._queue.put_nowait, (new_frame, datainfo))
            logger.debug(f"[BASE_REAL] Audio frame sent successfully")
            return
        except asyncio.QueueFull:
            logger.warning(f"[BASE_REAL] Queue full, dropping frame")
            return
        except Exception as e:
            logger.error(f"[BASE_REAL] Unexpected error: {e}")
            return

    # 回退到缓冲区
    with self._pending_audio_lock:
        self._pending_audio.append((new_frame, datainfo))
    logger.debug("[BASE_REAL] Loop not ready, buffered")


def fixed_webrtc_recv(self):
    """修复的WebRTC音频接收"""
    # ... 获取帧 ...

    if self.kind == 'audio':
        # 确保音频帧有正确的属性
        if not hasattr(frame, 'sample_rate'):
            frame.sample_rate = 16000
        if not hasattr(frame, 'samples'):
            frame.samples = 320

        sample_rate = frame.sample_rate
        n_samples = frame.samples

        # 初始化时间基准
        if not hasattr(self, "_timestamp"):
            self._start = time.time()
            self._timestamp = 0
            self.current_frame_count = 0

        # 计算PTS
        pts = self._timestamp
        frame.pts = pts
        frame.time_base = fractions.Fraction(1, sample_rate)

        # 推进时间戳
        self._timestamp += n_samples
        self.current_frame_count += 1

        # 🆕 关键修复：简化时间控制，避免过度等待
        expected_time = self._start + (self.current_frame_count * AUDIO_PTIME)
        wait_time = expected_time - time.time()

        if wait_time > 0:
            # 根据队列大小动态调整等待时间
            queue_size = self._queue.qsize()
            if queue_size > 40:
                # 队列充足，减少等待
                wait_time = min(wait_time, 0.005)
            elif queue_size > 20:
                # 队列正常，中等等待
                wait_time = min(wait_time, 0.01)
            else:
                # 队列不足，正常等待
                pass

            if wait_time > 0:
                await asyncio.sleep(wait_time)
        elif wait_time < -0.05:  # 调整阈值
            mylogger.warning(
                f"[WebRTC] Audio behind schedule: {wait_time:.3f}s")

    return frame


print("""
=== 修复要点 ===

1. DoubaoTTS.stream_audio:
   - 使用缓冲区处理不完整音频块
   - 不填充静音（避免噪音）
   - 只在最后处理剩余数据

2. BaseReal.put_audio_frame:
   - 移除大小检查和分块逻辑
   - 直接转换格式
   - 不手动设置samples属性

3. WebRTC.recv:
   - 简化时间控制
   - 减少过度等待
   - 根据队列大小动态调整

=== 根本原因 ===

噪音：填充静音产生爆音
卡顿：音频分块破坏连续性  
速度过快：重复处理或时间控制错误

=== 解决方案 ===

确保音频流连续、不重复、格式正确
""")
