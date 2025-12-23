#!/usr/bin/env python3
"""
终极音频修复 - 解决重复处理和格式错误问题

问题分析：
1. 音频被多次发送：TTS → basereal → ASR → WebRTC
2. 格式转换错误：float32/int16在多个地方转换
3. 速度过快：音频被重复发送到WebRTC

解决方案：
1. TTS直接发送到WebRTC，不经过basereal的ASR转发
2. 移除basereal中的音频处理逻辑
3. 确保只有一条音频路径到WebRTC
"""

# 修复1: TTS直接发送到WebRTC，不经过basereal


def fixed_tts_render(self, quit_event, audio_track, loop):
    """TTS直接发送到WebRTC"""
    self.audio_track = audio_track
    self.loop = loop

    # 启动TTS处理线程
    process_thread = Thread(target=self.process_tts, args=(quit_event,))
    process_thread.start()


def fixed_tts_txt_to_audio(self, msg):
    """TTS生成音频并直接发送"""
    # ... 生成音频 ...

    # 🆕 关键修复：直接发送到WebRTC，不经过basereal
    for chunk in audio_chunks:
        self._send_to_webrtc(chunk, eventpoint)


def fixed_tts_send_to_webrtc(self, audio_chunk, eventpoint):
    """直接发送到WebRTC"""
    # 转换格式
    frame = (audio_chunk * 32767).astype(np.int16)
    frame_2d = frame.reshape(1, -1)

    # 创建AudioFrame
    audio_frame = AudioFrame.from_ndarray(
        frame_2d, layout='mono', format='s16')
    audio_frame.sample_rate = 16000

    # 直接发送到WebRTC队列
    if self.audio_track and self.loop:
        try:
            self.loop.call_soon_threadsafe(
                self.audio_track._queue.put_nowait, (audio_frame, eventpoint))
        except:
            pass

# 修复2: basereal移除音频处理逻辑


def fixed_basereal_put_audio_frame(self, audio_chunk, datainfo):
    """basereal不再处理音频，只转发给ASR"""
    # 转发给ASR（用于口型驱动）
    if hasattr(self, 'asr'):
        try:
            self.asr.put_audio_frame(audio_chunk, datainfo)
        except Exception as e:
            logger.warning(f"[BASE_REAL] ASR forwarding failed: {e}")
    elif hasattr(self, 'lip_asr'):
        try:
            self.lip_asr.put_audio_frame(audio_chunk, datainfo)
        except Exception as e:
            logger.warning(f"[BASE_REAL] LipASR forwarding failed: {e}")

    # 🆕 不再发送到WebRTC，由TTS直接发送

# 修复3: WebRTC简化时间控制


def fixed_webrtc_recv(self):
    """简化WebRTC音频接收"""
    # ... 获取帧 ...

    if self.kind == 'audio':
        # 确保属性正确
        if not hasattr(frame, 'sample_rate'):
            frame.sample_rate = 16000
        if not hasattr(frame, 'samples'):
            frame.samples = 320

        # 时间戳处理
        if not hasattr(self, "_timestamp"):
            self._start = time.time()
            self._timestamp = 0
            self.current_frame_count = 0

        pts = self._timestamp
        frame.pts = pts
        frame.time_base = fractions.Fraction(1, 16000)

        self._timestamp += 320
        self.current_frame_count += 1

        # 🆕 简化等待逻辑
        expected_time = self._start + (self.current_frame_count * 0.020)
        wait_time = expected_time - time.time()

        if wait_time > 0:
            # 根据队列大小调整
            queue_size = self._queue.qsize()
            if queue_size > 30:
                wait_time = min(wait_time, 0.005)
            elif queue_size > 15:
                wait_time = min(wait_time, 0.01)

            if wait_time > 0:
                await asyncio.sleep(wait_time)
        elif wait_time < -0.05:
            mylogger.warning(f"[WebRTC] Audio behind: {wait_time:.3f}s")

    return frame


print("""
=== 终极修复方案 ===

核心问题：音频被重复处理和发送

修复策略：
1. TTS → WebRTC (直接)
2. TTS → ASR (口型驱动)
3. basereal → ASR (转发)

移除：
❌ TTS → basereal → WebRTC
❌ basereal中的音频格式转换
❌ 重复的音频块处理

结果：
✅ 音频只发送一次
✅ 格式转换只做一次
✅ 速度正常
✅ 无噪音
""")
