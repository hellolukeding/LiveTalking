"""
修复 DoubaoTTS 队列溢出问题的方案
==================================

方案1: 增加队列容量和添加异常处理
方案2: 实现流控机制
方案3: 使用缓冲区和重试机制
"""

import asyncio
import time
from typing import Optional


# 方案1: 修改 basereal.py 中的 put_audio_frame 方法
def put_audio_frame_fixed(self, audio_chunk, datainfo: dict = {}):
    """
    修复后的 put_audio_frame 方法，添加异常处理和重试机制
    """
    logger.debug(
        f"[BASE_REAL] put_audio_frame called: chunk_shape={audio_chunk.shape}, datainfo={datainfo}")

    # 转发给ASR（用于口型驱动）
    if hasattr(self, 'asr'):
        self.asr.put_audio_frame(audio_chunk, datainfo)
        logger.debug(f"[BASE_REAL] Sent frame to asr")
    elif hasattr(self, 'lip_asr'):
        self.lip_asr.put_audio_frame(audio_chunk, datainfo)
        logger.debug(
            f"[BASE_REAL] Sent frame to lip_asr, queue_size={self.lip_asr.queue.qsize()}")

    # 确保音频数据是正确的格式
    frame = (audio_chunk * 32767).astype(np.int16)

    # 创建音频帧
    if frame.ndim == 1:
        frame_2d = frame.reshape(1, -1)
        layout = 'mono'
    elif frame.ndim == 2:
        frame_2d = frame.reshape(1, -1)
        channels = frame.shape[1]
        layout = 'stereo' if channels == 2 else 'mono'
    else:
        frame_2d = frame.reshape(1, -1)
        layout = 'mono'

    new_frame = AudioFrame.from_ndarray(
        frame_2d, layout=layout, format='s16')
    new_frame.sample_rate = 16000

    # 如果 audio_track 未设置，则直接缓冲
    if not (hasattr(self, 'audio_track') and self.audio_track):
        with self._pending_audio_lock:
            self._pending_audio.append((new_frame, datainfo))
        logger.warning(
            "[BASE_REAL] Audio track not yet available - buffered frame for later flush")
        return

    # 尝试通过音轨队列的 loop 安全地放入帧，添加重试机制
    queue_loop = getattr(self.audio_track._queue, '_loop', None)
    if queue_loop and queue_loop.is_running():
        max_retries = 3
        retry_delay = 0.01  # 10ms

        for attempt in range(max_retries):
            try:
                queue_loop.call_soon_threadsafe(
                    self.audio_track._queue.put_nowait, (new_frame, datainfo))
                logger.debug(
                    f"[BASE_REAL] Forwarded audio to WebRTC track: {datainfo}")
                return  # 成功，退出函数
            except asyncio.QueueFull:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"[BASE_REAL] Queue full, retrying {attempt + 1}/{max_retries}...")
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        f"[BASE_REAL] Queue still full after {max_retries} attempts, dropping frame")
                    # 可选择：清空队列或丢弃旧帧
                    # self._drain_queue_if_needed()
                    return
            except Exception as e:
                logger.error(
                    f"[BASE_REAL] Unexpected error putting frame: {e}")
                return

    # 如果无法通过队列 loop 放入，则回退到缓冲区
    with self._pending_audio_lock:
        self._pending_audio.append((new_frame, datainfo))
    logger.warning(
        "[BASE_REAL] Audio track loop not ready - buffered frame for later flush")


# 方案2: 修改 webrtc.py 中的 PlayerStreamTrack 队列容量
class PlayerStreamTrackFixed(MediaStreamTrack):
    """
    修复后的 PlayerStreamTrack，使用更大的队列容量
    """

    def __init__(self, player, kind):
        super().__init__()
        self.kind = kind
        self._player = player
        # 增加队列容量到 500，避免溢出
        self._queue = asyncio.Queue(maxsize=500)
        self.timelist = []
        self.current_frame_count = 0
        if self.kind == 'video':
            self.framecount = 0
            self.lasttime = time.perf_counter()
            self.totaltime = 0


# 方案3: 实现流控机制，防止生产过快
class AudioFlowController:
    """
    音频流控器，控制音频帧的生成速度
    """

    def __init__(self, max_queue_size=200, target_queue_size=50):
        self.max_queue_size = max_queue_size
        self.target_queue_size = target_queue_size
        self.last_check_time = time.time()
        self.frame_count = 0

    def should_throttle(self, current_queue_size):
        """判断是否需要节流"""
        if current_queue_size >= self.max_queue_size:
            return True
        # 如果队列持续过大，也进行节流
        if current_queue_size >= self.target_queue_size * 2:
            return True
        return False

    def get_throttle_delay(self, current_queue_size):
        """根据队列大小计算节流延迟"""
        if current_queue_size >= self.max_queue_size:
            return 0.1  # 100ms 延迟
        elif current_queue_size >= self.target_queue_size * 2:
            return 0.05  # 50ms 延迟
        elif current_queue_size >= self.target_queue_size:
            return 0.02  # 20ms 延迟
        return 0


# 方案4: 修改 DoubaoTTS 的 stream_tts 方法，添加流控
async def stream_tts_with_flow_control(self, audio_stream, msg: tuple[str, dict]):
    """
    带流控的 stream_tts 方法
    """
    text, textevent = msg
    first = True
    last_stream = np.array([], dtype=np.float32)

    # 流控器
    flow_controller = AudioFlowController()

    logger.info(f"[DOUBAO_TTS stream_tts] Starting for text: '{text}'")
    chunk_count = 0

    async for chunk in audio_stream:
        if chunk is not None and len(chunk) > 0:
            chunk_count += 1
            logger.debug(
                f"[DOUBAO_TTS stream_tts] Processing chunk {chunk_count}, size: {len(chunk)}")

            # 检查队列大小并进行流控
            if hasattr(self.parent, 'audio_track') and self.parent.audio_track:
                queue_size = self.parent.audio_track._queue.qsize()
                if flow_controller.should_throttle(queue_size):
                    throttle_delay = flow_controller.get_throttle_delay(
                        queue_size)
                    logger.warning(
                        f"[DOUBAO_TTS] Queue size {queue_size} too high, throttling for {throttle_delay}s")
                    await asyncio.sleep(throttle_delay)

            stream = np.frombuffer(
                chunk, dtype=np.int16).astype(np.float32) / 32767
            stream = np.concatenate((last_stream, stream))
            streamlen = stream.shape[0]
            idx = 0

            while streamlen >= self.chunk:
                eventpoint = {}
                if first:
                    eventpoint = {'status': 'start', 'text': text}
                    eventpoint.update(**textevent)
                    first = False

                # 再次检查队列大小
                if hasattr(self.parent, 'audio_track') and self.parent.audio_track:
                    queue_size = self.parent.audio_track._queue.qsize()
                    if flow_controller.should_throttle(queue_size):
                        throttle_delay = flow_controller.get_throttle_delay(
                            queue_size)
                        logger.warning(
                            f"[DOUBAO_TTS] Queue size {queue_size} during processing, throttling for {throttle_delay}s")
                        await asyncio.sleep(throttle_delay)

                self.parent.put_audio_frame(
                    stream[idx:idx + self.chunk], eventpoint)
                streamlen -= self.chunk
                idx += self.chunk
            last_stream = stream[idx:]

        # 添加小延迟，避免处理过快
        await asyncio.sleep(0.001)

    eventpoint = {'status': 'end', 'text': text}
    eventpoint.update(**textevent)
    self.parent.put_audio_frame(
        np.zeros(self.chunk, np.float32), eventpoint)


print("修复方案总结:")
print("1. 增加队列容量: 从 100 增加到 500")
print("2. 添加重试机制: 在 put_audio_frame 中实现重试逻辑")
print("3. 实现流控: 根据队列大小动态调整处理速度")
print("4. 改进异常处理: 避免单个错误导致整个系统崩溃")
print("\n推荐使用方案1 + 方案2的组合，既简单又有效。")
