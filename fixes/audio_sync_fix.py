"""
LiveTalking 音频同步和TTS播放修复方案
=====================================

修复内容：
1. TTS卡顿和失声问题
2. 音画不同步问题
3. 音频队列溢出问题
4. WebRTC音频时间戳问题
"""

import asyncio
import time
from queue import Queue
from threading import Lock

import numpy as np
from av import AudioFrame

from logger import logger


class AudioSyncFix:
    """音频同步修复类"""

    def __init__(self):
        # 音频缓冲区，用于平滑播放
        self.audio_buffer = []
        self.buffer_lock = Lock()

        # 时间同步相关
        self.audio_start_time = None
        self.video_start_time = None
        self.audio_frames_sent = 0
        self.video_frames_sent = 0

        # 流控参数
        self.target_queue_size = 30  # 目标队列大小
        self.max_queue_size = 100    # 最大队列大小
        self.throttle_threshold = 50  # 开始节流的阈值

        # 性能监控
        self.frame_count = 0
        self.last_log_time = time.time()

    def calculate_audio_delay(self, queue_size):
        """根据队列大小计算合适的延迟"""
        if queue_size >= self.max_queue_size:
            return 0.1  # 100ms
        elif queue_size >= self.throttle_threshold:
            return 0.05  # 50ms
        elif queue_size >= self.target_queue_size:
            return 0.02  # 20ms
        return 0

    def sync_audio_video(self, audio_track, video_track):
        """同步音频和视频轨道"""
        if not hasattr(self, 'sync_start_time'):
            self.sync_start_time = time.time()
            return

        # 计算时间差
        elapsed = time.time() - self.sync_start_time
        expected_audio_frames = elapsed / 0.02  # 20ms per frame
        expected_video_frames = elapsed / 0.04  # 40ms per frame

        # 如果音频帧过多，适当延迟
        if audio_track and audio_track._queue:
            audio_qsize = audio_track._queue.qsize()
            if audio_qsize > 60:  # 超过1.2秒的音频
                delay = (audio_qsize - 60) * 0.02
                logger.warning(
                    f"Audio queue too large ({audio_qsize}), delaying {delay:.3f}s")
                return delay

        return 0


# 全局音频同步器
audio_sync = AudioSyncFix()

# 修复后的 put_audio_frame 方法


def fixed_put_audio_frame(self, audio_chunk, datainfo: dict = {}):
    """
    修复的音频帧处理方法，解决卡顿和同步问题
    """
    # 确保音频数据格式正确
    if not isinstance(audio_chunk, np.ndarray):
        logger.error(f"[FIX] Invalid audio chunk type: {type(audio_chunk)}")
        return

    # 转换为正确的格式
    frame = (audio_chunk * 32767).astype(np.int16)

    # 创建音频帧
    if frame.ndim == 1:
        frame_2d = frame.reshape(1, -1)
        layout = 'mono'
    elif frame.ndim == 2:
        frame_2d = frame.reshape(1, -1)
        layout = 'mono'
    else:
        logger.warning(
            f"[FIX] Unexpected audio shape: {frame.shape}, flattening")
        frame_2d = frame.reshape(1, -1)
        layout = 'mono'

    try:
        new_frame = AudioFrame.from_ndarray(
            frame_2d, layout=layout, format='s16')
        new_frame.sample_rate = 16000
    except Exception as e:
        logger.error(f"[FIX] Failed to create AudioFrame: {e}")
        return

    # 转发给ASR
    if hasattr(self, 'asr'):
        try:
            self.asr.put_audio_frame(audio_chunk, datainfo)
        except Exception as e:
            logger.warning(f"[FIX] ASR forwarding failed: {e}")
    elif hasattr(self, 'lip_asr'):
        try:
            self.lip_asr.put_audio_frame(audio_chunk, datainfo)
        except Exception as e:
            logger.warning(f"[FIX] LipASR forwarding failed: {e}")

    # WebRTC转发逻辑
    if not (hasattr(self, 'audio_track') and self.audio_track):
        with self._pending_audio_lock:
            self._pending_audio.append((new_frame, datainfo))
        logger.debug("[FIX] Audio track not ready, buffered")
        return

    # 检查队列大小并应用流控
    queue_size = self.audio_track._queue.qsize()
    delay = audio_sync.calculate_audio_delay(queue_size)

    if delay > 0:
        logger.debug(
            f"[FIX] Queue size {queue_size}, applying {delay:.3f}s delay")
        time.sleep(delay)

    # 尝试安全地放入队列
    queue_loop = getattr(self.audio_track._queue, '_loop', None)
    if queue_loop and queue_loop.is_running():
        max_retries = 5
        retry_delay = 0.005

        for attempt in range(max_retries):
            try:
                queue_loop.call_soon_threadsafe(
                    self.audio_track._queue.put_nowait, (new_frame, datainfo))
                logger.debug(f"[FIX] Audio frame sent successfully")

                # 性能监控
                audio_sync.frame_count += 1
                current_time = time.time()
                if current_time - audio_sync.last_log_time > 5:
                    fps = audio_sync.frame_count / \
                        (current_time - audio_sync.last_log_time)
                    logger.info(
                        f"[FIX] Audio FPS: {fps:.2f}, Queue: {queue_size}")
                    audio_sync.frame_count = 0
                    audio_sync.last_log_time = current_time

                return
            except asyncio.QueueFull:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"[FIX] Queue full, retry {attempt + 1}/{max_retries}")
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        f"[FIX] Queue still full after {max_retries} attempts")
                    # 清理旧帧
                    try:
                        while self.audio_track._queue.qsize() > 50:
                            self.audio_track._queue.get_nowait()
                        logger.info("[FIX] Cleared old audio frames")
                    except:
                        pass
                    return
            except Exception as e:
                logger.error(f"[FIX] Unexpected error: {e}")
                return

    # 回退到缓冲区
    with self._pending_audio_lock:
        self._pending_audio.append((new_frame, datainfo))
    logger.debug("[FIX] Loop not ready, buffered")

# 修复后的WebRTC音频时间戳处理


def fixed_audio_recv(self):
    """修复音频接收的时间戳问题"""
    frame, eventpoint = self._queue.get()

    if frame is None:
        self.stop()
        raise Exception

    if self.kind == 'audio':
        # 使用更精确的时间戳计算
        sample_rate = getattr(frame, 'sample_rate', 16000)
        n_samples = getattr(frame, 'samples', 320)

        # 初始化时间基准
        if not hasattr(self, "_timestamp"):
            self._start = time.time()
            self._timestamp = 0
            self.current_frame_count = 0
            self.timelist.append(self._start)
            logger.info(f'audio start:{self._start}')

        # 计算PTS和时间基准
        pts = self._timestamp
        frame.pts = pts
        frame.time_base = fractions.Fraction(1, sample_rate)

        # 推进时间戳
        self._timestamp += n_samples
        self.current_frame_count += 1

        # 精确的时间控制
        expected_time = self._start + (self._timestamp / sample_rate)
        wait_time = expected_time - time.time()

        # 只在需要时等待，避免过度延迟
        if wait_time > 0:
            if wait_time > 0.1:  # 如果等待时间过长，可能是队列问题
                logger.warning(
                    f"[FIX] Large audio wait time: {wait_time:.3f}s")
            await asyncio.sleep(min(wait_time, 0.05))  # 限制最大等待时间
    else:
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base

    if eventpoint and self._player is not None:
        self._player.notify(eventpoint)

    return frame

# 修复后的TTS流式处理


async def fixed_tts_stream(self, audio_array, msg: tuple[str, dict]):
    """修复TTS流式处理，避免卡顿"""
    text, textevent = msg
    streamlen = audio_array.shape[0]
    idx = 0
    first = True

    logger.debug(f"[FIX_TTS] Starting stream, total length: {streamlen}")

    # 计算需要的块数
    chunks_needed = streamlen // self.chunk
    if chunks_needed == 0:
        logger.warning(f"[FIX_TTS] Audio too short: {streamlen} samples")
        return

    # 流控参数
    frames_sent = 0
    last_check_time = time.time()

    while streamlen >= self.chunk and self.state == State.RUNNING:
        eventpoint = {}

        if first:
            eventpoint = {'status': 'start', 'text': text}
            eventpoint.update(**textevent)
            first = False

        # 发送音频块
        audio_chunk = audio_array[idx:idx + self.chunk]
        self.parent.put_audio_frame(audio_chunk, eventpoint)

        frames_sent += 1
        streamlen -= self.chunk
        idx += self.chunk

        # 每10帧检查一次队列状态
        if frames_sent % 10 == 0 and hasattr(self.parent, 'audio_track') and self.parent.audio_track:
            queue_size = self.parent.audio_track._queue.qsize()

            # 动态调整处理速度
            if queue_size > 80:
                delay = 0.02
                logger.debug(
                    f"[FIX_TTS] Queue high ({queue_size}), delay {delay}s")
                await asyncio.sleep(delay)
            elif queue_size > 40:
                delay = 0.01
                await asyncio.sleep(delay)

        # 小延迟避免CPU占用过高
        await asyncio.sleep(0.001)

    # 发送结束事件
    eventpoint = {'status': 'end', 'text': text}
    eventpoint.update(**textevent)
    self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)

    logger.debug(f"[FIX_TTS] Stream completed, {frames_sent} frames sent")

print("音频同步修复方案已生成")
print("主要修复点：")
print("1. 流控机制：根据队列大小动态调整处理速度")
print("2. 时间戳精确计算：使用实际样本数而非固定值")
print("3. 重试机制：处理队列满的情况")
print("4. 性能监控：实时监控音频FPS和队列状态")
print("5. 避免过度缓冲：限制最大延迟时间")
